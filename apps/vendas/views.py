from django.db import transaction
from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from .models import SessaoCaixa, Venda, VendaItem, VendaPagamento, OperacaoCaixa
from .serializers import (
    SessaoCaixaSerializer,
    VendaSerializer,
    VendaReadSerializer,
    VendaItemSerializer,
    VendaPagamentoSerializer,
    OperacaoCaixaSerializer,
    VendaFinalizarSerializer,
)

@extend_schema(tags=['Caixa'])
class SessaoCaixaViewSet(viewsets.ModelViewSet):
    queryset = SessaoCaixa.objects.all().select_related('operador')
    serializer_class = SessaoCaixaSerializer
    def get_queryset(self):
        queryset = super().get_queryset()
        data_inicio = self.request.query_params.get('data_inicio')
        data_fim = self.request.query_params.get('data_fim')

        if data_inicio:
            queryset = queryset.filter(data_abertura__date__gte=data_inicio)
        if data_fim:
            queryset = queryset.filter(data_abertura__date__lte=data_fim)

        return queryset.order_by('-data_abertura')

    def perform_create(self, serializer):
        serializer.save(operador=self.request.user)

    @action(detail=False, methods=['get'], url_path='ativa')
    def sessao_ativa(self, request):
        """Retorna a sessão de caixa aberta do usuário atual, se houver."""
        sessao = SessaoCaixa.objects.filter(operador=request.user, status='ABERTA').last()
        if sessao:
            return Response(SessaoCaixaSerializer(sessao).data)
        return Response(None)

    @action(detail=True, methods=['post'], url_path='fechar')
    def fechar(self, request, pk=None):
        """Fecha a sessão de caixa e retorna o resumo financeiro."""
        from django.utils import timezone
        sessao = self.get_object()

        if sessao.status == 'FECHADA':
            return Response({'erro': 'Este caixa já está fechado.'}, status=400)

        # Impede fechar se houver vendas em aberto
        vendas_abertas = Venda.objects.filter(sessao=sessao, status='EM_ABERTO').exists()
        if vendas_abertas:
            return Response({'erro': 'Não é possível fechar o caixa com vendas em aberto. Finalize ou cancele as vendas pendentes.'}, status=400)

        # Calcula resumo
        vendas = Venda.objects.filter(sessao=sessao, status='FINALIZADA')
        pagamentos = VendaPagamento.objects.filter(venda__in=vendas)

        resumo = {
            'total_vendas': sum(v.total for v in vendas),
            'quantidade_vendas': vendas.count(),
            'por_forma': {}
        }

        for forma, label in VendaPagamento.FORMA_CHOICES:
            total_forma = sum(p.valor for p in pagamentos if p.forma == forma)
            resumo['por_forma'][forma] = total_forma

        sessao.status = 'FECHADA'
        sessao.data_fechamento = timezone.now()
        sessao.save()

        return Response({
            'sessao': SessaoCaixaSerializer(sessao).data,
            'resumo': resumo
        })

    @action(detail=True, methods=['post'], url_path='sangria')
    def sangria(self, request, pk=None):
        sessao = self.get_object()
        if sessao.status == 'FECHADA':
            return Response({'erro': 'Caixa fechado.'}, status=400)

        valor = request.data.get('valor')
        motivo = request.data.get('motivo', '')

        if not valor or float(valor) <= 0:
            return Response({'erro': 'Valor inválido.'}, status=400)

        op = OperacaoCaixa.objects.create(
            sessao=sessao, tipo='SANGRIA', valor=valor, motivo=motivo
        )
        return Response(OperacaoCaixaSerializer(op).data, status=201)

    @action(detail=True, methods=['post'], url_path='suprimento')
    def suprimento(self, request, pk=None):
        sessao = self.get_object()
        if sessao.status == 'FECHADA':
            return Response({'erro': 'Caixa fechado.'}, status=400)

        valor = request.data.get('valor')
        motivo = request.data.get('motivo', '')

        if not valor or float(valor) <= 0:
            return Response({'erro': 'Valor inválido.'}, status=400)

        op = OperacaoCaixa.objects.create(
            sessao=sessao, tipo='SUPRIMENTO', valor=valor, motivo=motivo
        )
        return Response(OperacaoCaixaSerializer(op).data, status=201)


@extend_schema(tags=['Vendas'])
class VendaViewSet(viewsets.ModelViewSet):
    queryset = Venda.objects.all().select_related(
        'cliente', 'sessao', 'sessao__operador'
    ).prefetch_related(
        'itens__produto', 'pagamentos'
    )
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['data', 'total', 'status']

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve', 'finalizar', 'cancelar']:
            return VendaReadSerializer
        return VendaSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        sessao = self.request.query_params.get('sessao')
        status = self.request.query_params.get('status')
        data_inicio = self.request.query_params.get('data_inicio')
        data_fim = self.request.query_params.get('data_fim')

        if sessao:
            queryset = queryset.filter(sessao_id=sessao)
        if status:
            queryset = queryset.filter(status=status)
        if data_inicio:
            queryset = queryset.filter(data__date__gte=data_inicio)
        if data_fim:
            queryset = queryset.filter(data__date__lte=data_fim)

        return queryset.order_by('-data')

    @extend_schema(
        summary="Salvar venda como orçamento",
        description="Marca a venda atual como ORCAMENTO sem baixar estoque e sem exigir pagamentos.",
        responses={200: VendaReadSerializer}
    )
    @action(detail=True, methods=['post'], url_path='salvar-orcamento')
    def salvar_orcamento(self, request, pk=None):
        venda = self.get_object()

        if venda.status != 'EM_ABERTO':
            return Response({'erro': 'Apenas vendas em aberto podem ser salvas como orçamento.'}, status=400)

        cliente_id = request.data.get('cliente')

        from decimal import Decimal, ROUND_HALF_UP
        def quantize(val):
            return Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        desconto = quantize(request.data.get('desconto', 0))

        venda.status = 'ORCAMENTO'
        venda.desconto = desconto
        if cliente_id:
            venda.cliente_id = cliente_id

        venda.save()

        return Response(VendaReadSerializer(venda).data)

    @extend_schema(
        summary="Finalizar uma venda",
        description="Fecha a venda, registra os pagamentos e baixa o estoque.",
        request=VendaFinalizarSerializer,
        responses={200: VendaReadSerializer}
    )
    @action(detail=True, methods=['post'], url_path='finalizar')
    def finalizar(self, request, pk=None):
        # ... (Logica de finalização mantida igual, apenas retornando o serializer correto)
        venda = self.get_object()

        if venda.status != 'EM_ABERTO':
            return Response({'erro': 'Apenas vendas em aberto podem ser finalizadas.'}, status=400)

        pagamentos_data = request.data.get('pagamentos', [])
        cliente_id = request.data.get('cliente')

        if not pagamentos_data:
            return Response({'erro': 'Informe ao menos uma forma de pagamento.'}, status=400)

        from decimal import Decimal, ROUND_HALF_UP
        def quantize(val):
            return Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        desconto = quantize(request.data.get('desconto', 0))
        total_pago = quantize(sum(Decimal(str(p.get('valor', 0))) for p in pagamentos_data))
        total_liquido = quantize(venda.total - desconto)

        if total_pago < total_liquido - Decimal('0.05'):
             return Response({
                 'erro': f'O total dos pagamentos (R${total_pago:.2f}) não atinge o total líquido da venda (R${total_liquido:.2f}).'
             }, status=400)

        troco = total_pago - total_liquido
        if troco > Decimal('0.05'):
            pagamento_dinheiro = next((p for p in pagamentos_data if str(p.get('forma', '')).strip().upper() == 'DINHEIRO'), None)

            if pagamento_dinheiro:
                valor_em_dinheiro = Decimal(str(pagamento_dinheiro.get('valor', 0)))
                if troco > valor_em_dinheiro + Decimal('0.05'):
                     return Response({
                        'erro': 'O troco é maior do que o valor pago em dinheiro, o que é inválido.'
                     }, status=400)

                # Abate o troco no pagamento em dinheiro para que o caixa físico bata
                pagamento_dinheiro['valor'] = float(valor_em_dinheiro - troco)
            else:
                # Se não tem dinheiro, mas o total é maior (ex: PIX arredondado pra cima)
                # Apenas deixamos passar, o valor registrado será o valor cheio enviado.
                pass
        try:
            with transaction.atomic():
                itens = venda.itens.select_related('produto').all()
                if not itens:
                    raise ValueError('O carrinho está vazio.')

                from apps.produtos.services import registrar_movimentacao

                for item in itens:
                    registrar_movimentacao(
                        produto_id=item.produto_id,
                        quantidade=item.quantidade,
                        tipo='SAIDA',
                        motivo='VENDA',
                        loja='Loja Principal',
                        observacoes=f'Venda #{venda.id}'
                    )

                for p in pagamentos_data:
                    VendaPagamento.objects.create(venda=venda, forma=p['forma'], valor=p['valor'])

                    # Se for FIADO, gera Conta a Receber
                    if str(p['forma']).strip().upper() == 'FIADO':
                        from apps.financeiro.models import ContaReceber
                        from django.utils import timezone
                        from datetime import timedelta

                        nome_cliente = "Consumidor Final"
                        if cliente_id:
                            from apps.clientes.models import Cliente
                            try:
                                cli = Cliente.objects.get(id=cliente_id)
                                nome_cliente = cli.nome
                            except:
                                pass
                        elif venda.cliente:
                            nome_cliente = venda.cliente.nome

                        ContaReceber.objects.create(
                            descricao=f"Venda FIADO #{venda.id}",
                            cliente_nome=nome_cliente,
                            valor=p['valor'],
                            vencimento=timezone.now().date() + timedelta(days=30), # Padrão 30 dias
                            status='PENDENTE',
                            observacoes=f'Originada da Venda #{venda.id} no PDV.'
                        )

                # SUCESSO TOTAL: Agora sim finalizamos a venda
                venda.status = 'FINALIZADA'
                venda.desconto = desconto
                if cliente_id:
                    venda.cliente_id = cliente_id

                venda.save()

        except Exception as e:
            return Response({'erro': f'Erro ao finalizar: {str(e)}'}, status=400)

        return Response(VendaReadSerializer(venda).data)

    @action(detail=True, methods=['post'], url_path='cancelar')
    def cancelar(self, request, pk=None):
        venda = self.get_object()
        if venda.status == 'CANCELADA':
            return Response({'erro': 'Esta venda já está cancelada.'}, status=400)

        try:
            with transaction.atomic():
                if venda.status == 'FINALIZADA':
                    from apps.produtos.services import registrar_movimentacao
                    for item in venda.itens.all():
                        registrar_movimentacao(
                            produto_id=item.produto_id,
                            quantidade=item.quantidade,
                            tipo='ENTRADA',
                            motivo='DEVOLUCAO',
                            loja='Loja Principal',
                            observacoes=f'Estorno Venda #{venda.id} (Cancelamento)'
                        )

                venda.status = 'CANCELADA'
                venda.save()
        except Exception as e:
            return Response({'erro': str(e)}, status=400)

        return Response(VendaReadSerializer(venda).data)

class VendaItemViewSet(viewsets.ModelViewSet):
    queryset = VendaItem.objects.all().select_related('produto')
    serializer_class = VendaItemSerializer


class VendaPagamentoViewSet(viewsets.ModelViewSet):
    queryset = VendaPagamento.objects.all()
    serializer_class = VendaPagamentoSerializer

class OperacaoCaixaViewSet(viewsets.ModelViewSet):
    queryset = OperacaoCaixa.objects.all()
    serializer_class = OperacaoCaixaSerializer

def comprovante_venda_publico(request, id_externo):
    """View pública para exibir o comprovante da venda via link compartilhado"""
    venda = get_object_or_404(Venda, id_externo=id_externo)
    return render(request, 'vendas/comprovante.html', {'venda': venda})
