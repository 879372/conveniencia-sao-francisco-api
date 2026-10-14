from django.db import transaction
from .models import Produto, EstoqueLoja, MovimentacaoEstoque

def registrar_movimentacao(produto_id, quantidade, tipo, motivo, loja='Loja Principal', observacoes=''):
    """
    Registra uma movimentação no estoque (Kardex) e atualiza o saldo atual em EstoqueLoja.
    quantidade: valor positivo (a lógica de soma/subtração depende do 'tipo')
    """
    with transaction.atomic():
        # 1. Busca ou cria o registro de estoque na loja
        estoque, created = EstoqueLoja.objects.get_or_create(
            produto_id=produto_id,
            loja=loja,
            defaults={'quantidade': 0}
        )

        saldo_anterior = estoque.quantidade

        # 2. Calcula novo saldo
        if tipo == 'ENTRADA':
            estoque.quantidade += quantidade
        else:
            if estoque.quantidade < quantidade:
                # Opcional: Levantar erro se estoque ficar negativo,
                # mas para hortifruti as vezes permite-se vender sem estoque e ajustar depois
                pass
            estoque.quantidade -= quantidade

        estoque.save()

        # 3. Cria o registro no Kardex
        mov = MovimentacaoEstoque.objects.create(
            produto_id=produto_id,
            tipo=tipo,
            motivo=motivo,
            quantidade=quantidade,
            saldo_anterior=saldo_anterior,
            saldo_atual=estoque.quantidade,
            observacoes=observacoes
        )

        return mov
