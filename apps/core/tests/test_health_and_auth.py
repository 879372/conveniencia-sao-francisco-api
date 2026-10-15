import pytest


@pytest.mark.django_db
def test_health_check_publico(api_client):
    response = api_client.get('/api/health/')
    assert response.status_code == 200
    assert response.data['status'] == 'ok'
    assert response.data['database'] == 'connected'


@pytest.mark.django_db
def test_login_jwt(api_client, admin_user):
    response = api_client.post('/api/auth/login/', {
        'username': admin_user.username,
        'password': 'testpassword123',
    }, format='json')
    assert response.status_code == 200
    assert response.data['access']
    assert response.data['refresh']


@pytest.mark.django_db
def test_dashboard_exige_autenticacao(api_client):
    response = api_client.get('/api/dashboard-stats/')
    assert response.status_code == 401
