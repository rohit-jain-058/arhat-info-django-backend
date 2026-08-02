import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()


# ── Fixtures ──────────────────────────────────────────────────────────
@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_data():
    return {
        'email':      'test@example.com',
        'first_name': 'Test',
        'last_name':  'User',
        'password':   'StrongPass123!',
        'password2':  'StrongPass123!',
    }


@pytest.fixture
def create_user(db):
    def _create(email='user@example.com', password='StrongPass123!', **kwargs):
        return User.objects.create_user(email=email, password=password, **kwargs)
    return _create


@pytest.fixture
def auth_client(api_client, create_user):
    user = create_user()
    url  = reverse('token_obtain_pair')
    res  = api_client.post(url, {'email': 'user@example.com', 'password': 'StrongPass123!'}, format='json')
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
    api_client.user = user
    return api_client


# ── Registration ──────────────────────────────────────────────────────
@pytest.mark.django_db
class TestRegistration:

    def test_register_success(self, api_client, user_data):
        url = reverse('register')
        res = api_client.post(url, user_data, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        assert 'tokens' in res.data
        assert 'access'  in res.data['tokens']
        assert 'refresh' in res.data['tokens']
        assert res.data['user']['email'] == user_data['email']

    def test_register_duplicate_email(self, api_client, user_data, create_user):
        create_user(email=user_data['email'])
        url = reverse('register')
        res = api_client.post(url, user_data, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_passwords_mismatch(self, api_client, user_data):
        user_data['password2'] = 'DifferentPass!'
        url = reverse('register')
        res = api_client.post(url, user_data, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_missing_email(self, api_client, user_data):
        del user_data['email']
        url = reverse('register')
        res = api_client.post(url, user_data, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST


# ── Login / JWT ───────────────────────────────────────────────────────
@pytest.mark.django_db
class TestLogin:

    def test_login_success(self, api_client, create_user):
        create_user(email='login@example.com', password='StrongPass123!')
        url = reverse('token_obtain_pair')
        res = api_client.post(url, {'email': 'login@example.com', 'password': 'StrongPass123!'}, format='json')
        assert res.status_code == status.HTTP_200_OK
        assert 'access'  in res.data
        assert 'refresh' in res.data

    def test_login_wrong_password(self, api_client, create_user):
        create_user(email='login@example.com', password='StrongPass123!')
        url = reverse('token_obtain_pair')
        res = api_client.post(url, {'email': 'login@example.com', 'password': 'WrongPass!'}, format='json')
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_nonexistent_user(self, api_client):
        url = reverse('token_obtain_pair')
        res = api_client.post(url, {'email': 'noone@example.com', 'password': 'pass'}, format='json')
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_token_refresh(self, api_client, create_user):
        create_user()
        login_url   = reverse('token_obtain_pair')
        refresh_url = reverse('token_refresh')
        login_res   = api_client.post(login_url, {'email': 'user@example.com', 'password': 'StrongPass123!'}, format='json')
        refresh_res = api_client.post(refresh_url, {'refresh': login_res.data['refresh']}, format='json')
        assert refresh_res.status_code == status.HTTP_200_OK
        assert 'access' in refresh_res.data


# ── Profile ───────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestProfile:

    def test_get_profile(self, auth_client):
        url = reverse('user_profile')
        res = auth_client.get(url)
        assert res.status_code == status.HTTP_200_OK
        assert res.data['email'] == auth_client.user.email

    def test_update_profile(self, auth_client):
        url = reverse('user_profile')
        res = auth_client.patch(url, {'first_name': 'Updated'}, format='json')
        assert res.status_code == status.HTTP_200_OK
        assert res.data['first_name'] == 'Updated'

    def test_profile_requires_auth(self, api_client):
        url = reverse('user_profile')
        res = api_client.get(url)
        assert res.status_code == status.HTTP_401_UNAUTHORIZED


# ── Logout ────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestLogout:

    def test_logout_blacklists_token(self, api_client, create_user):
        create_user()
        login_url  = reverse('token_obtain_pair')
        logout_url = reverse('logout')
        login_res  = api_client.post(login_url, {'email': 'user@example.com', 'password': 'StrongPass123!'}, format='json')
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_res.data['access']}")
        res = api_client.post(logout_url, {'refresh': login_res.data['refresh']}, format='json')
        assert res.status_code == status.HTTP_205_RESET_CONTENT

    def test_logout_invalid_token(self, auth_client):
        url = reverse('logout')
        res = auth_client.post(url, {'refresh': 'badtoken'}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST


# ── Change password ───────────────────────────────────────────────────
@pytest.mark.django_db
class TestChangePassword:

    def test_change_password_success(self, auth_client):
        url = reverse('change_password')
        res = auth_client.put(url, {
            'old_password': 'StrongPass123!',
            'new_password': 'NewStrongPass456!',
        }, format='json')
        assert res.status_code == status.HTTP_200_OK

    def test_change_password_wrong_old(self, auth_client):
        url = reverse('change_password')
        res = auth_client.put(url, {
            'old_password': 'WrongOldPass!',
            'new_password': 'NewStrongPass456!',
        }, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
