from decimal import Decimal

import pytest

from apps.financeiro.models import ContaPagar
from apps.produtos.models import EstoqueLoja, MovimentacaoEstoque
from apps.produtos.tests.factories import EstoqueLojaFactory


@pytest.mark.django_db
def test_registrar_e_receber_compra_atualiza_estoque_e_financeiro(auth_client):
    estoque = EstoqueLojaFactory(
        quantidade=Decimal('4.000'),
        loja='Loja Principal',
    )
    payload = {
        'numero_documento': 'COMPRA-001',
        'fornecedor': 'Fornecedor Teste',
        'valor_total': '37.50',
        'itens': [{
            'produto': estoque.produto_id,
            'descricao': estoque.produto.nome,
            'quantidade': '3.000',
            'valor_unitario': '12.50',
            'subtotal': '37.50',
        }],
    }

    criada = auth_client.post('/api/compras/', payload, format='json')
    assert criada.status_code == 201
    assert 'xml_nfe' not in criada.data
    assert 'chave_acesso' not in criada.data

    recebida = auth_client.post(
        f"/api/compras/{criada.data['id']}/receber/",
        {},
        format='json',
    )
    assert recebida.status_code == 200

    estoque.refresh_from_db()
    assert estoque.quantidade == Decimal('7.000')
    assert MovimentacaoEstoque.objects.filter(
        produto=estoque.produto,
        tipo='ENTRADA',
        motivo='COMPRA',
    ).exists()
    assert ContaPagar.objects.filter(
        fornecedor='Fornecedor Teste',
        valor=Decimal('37.50'),
    ).exists()


@pytest.mark.django_db
def test_rotas_fiscais_nao_existem(auth_client):
    assert auth_client.get('/api/fiscal/').status_code == 404
    assert auth_client.post('/api/vendas/1/emitir-nfce/', {}, format='json').status_code == 404
