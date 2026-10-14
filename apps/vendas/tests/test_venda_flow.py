import pytest
from decimal import Decimal
from apps.vendas.tests.factories import VendaFactory, VendaItemFactory, SessaoCaixaFactory
from apps.produtos.tests.factories import EstoqueLojaFactory
from apps.vendas.models import Venda

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
