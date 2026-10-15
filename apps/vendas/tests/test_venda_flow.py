import pytest
from decimal import Decimal
from apps.vendas.tests.factories import VendaFactory, VendaItemFactory, SessaoCaixaFactory
from apps.produtos.tests.factories import EstoqueLojaFactory
from apps.vendas.models import Venda, VendaPagamento

@pytest.mark.django_db
def test_finalizar_venda_sucesso(auth_client, admin_user):
    """
    Testa o fluxo completo de finalização de uma venda e baixa de estoque.
    """
    # 1. Setup Data
    sessao = SessaoCaixaFactory(operador=admin_user)
    venda = VendaFactory(sessao=sessao, total=Decimal("50.00"), status="EM_ABERTO")

    estoque = EstoqueLojaFactory(quantidade=Decimal("10.00"), loja="Loja Principal")
    item = VendaItemFactory(
        venda=venda,
        produto=estoque.produto,
        quantidade=Decimal("2.00"),
        preco_unitario=Decimal("25.00"),
        subtotal=Decimal("50.00")
    )

    # 2. Execute Action
    payload = {
        "pagamentos": [
            {"forma": "DINHEIRO", "valor": "50.00"}
        ]
    }

    url = f"/api/vendas/{venda.id}/finalizar/"
    response = auth_client.post(url, payload, format='json')

    # 3. Assertions
    assert response.status_code == 200

    venda.refresh_from_db()
    assert venda.status == "FINALIZADA"

    estoque.refresh_from_db()
    # 10.00 inicial - 2.00 vendidos = 8.00
    assert estoque.quantidade == Decimal("8.00")

    # Verifica se criou o pagamento
    assert venda.pagamentos.count() == 1
    assert venda.pagamentos.first().forma == "DINHEIRO"

@pytest.mark.django_db
def test_finalizar_venda_total_divergente(auth_client, admin_user):
    """
    Deve retornar 400 se o total pago não bater com o total da venda.
    """
    venda = VendaFactory(total=Decimal("100.00"), status="EM_ABERTO")
    VendaItemFactory(venda=venda, subtotal=Decimal("100.00"))

    payload = {
        "pagamentos": [
            {"forma": "PIX", "valor": "90.00"} # Valor errado
        ]
    }

    url = f"/api/vendas/{venda.id}/finalizar/"
    response = auth_client.post(url, payload, format='json')

    assert response.status_code == 400
    assert "não atinge" in response.data['erro']


@pytest.mark.django_db
def test_fechar_caixa_exige_conferencia_e_calcula_diferenca(auth_client, admin_user):
    sessao = SessaoCaixaFactory(
        operador=admin_user,
        fundo_inicial=Decimal('100.00'),
        status='ABERTA',
    )
    venda = VendaFactory(sessao=sessao, total=Decimal('50.00'), status='FINALIZADA')
    VendaPagamento.objects.create(venda=venda, forma='DINHEIRO', valor=Decimal('50.00'))

    sem_valor = auth_client.post(f'/api/sessoes-caixa/{sessao.id}/fechar/', {}, format='json')
    assert sem_valor.status_code == 400
    assert 'valor contado' in sem_valor.data['erro'].lower()

    resposta = auth_client.post(
        f'/api/sessoes-caixa/{sessao.id}/fechar/',
        {'valor_contado': '148.00'},
        format='json',
    )
    assert resposta.status_code == 200
    assert Decimal(str(resposta.data['resumo']['valor_esperado'])) == Decimal('150.00')
    assert Decimal(str(resposta.data['resumo']['diferenca'])) == Decimal('-2.00')

    sessao.refresh_from_db()
    assert sessao.status == 'FECHADA'
    assert sessao.valor_contado == Decimal('148.00')
    assert sessao.diferenca_caixa == Decimal('-2.00')
