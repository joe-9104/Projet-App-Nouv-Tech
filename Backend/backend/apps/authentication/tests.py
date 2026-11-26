from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient


class AuthenticationTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_login_me_logout(self):
        response = self.client.post('/api/auth/register/', {
            'email': 'student@example.com', 'password': 'Strong-Password-2026!',
            'first_name': 'Ada', 'last_name': 'Student',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn('password', str(response.data).lower())

        self.client.post('/api/auth/logout/', {}, format='json')
        response = self.client.post('/api/auth/login/', {
            'email': 'student@example.com', 'password': 'Strong-Password-2026!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        me = self.client.get('/api/auth/me/')
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data['user']['email'], 'student@example.com')

        logout = self.client.post('/api/auth/logout/', {}, format='json')
        self.assertEqual(logout.status_code, status.HTTP_200_OK)
        self.assertIn(self.client.get('/api/auth/me/').status_code, (401, 403))

    def test_duplicate_and_invalid_registration(self):
        User.objects.create_user(username='existing', email='same@example.com', password='Strong-Password-2026!')
        duplicate = self.client.post('/api/auth/register/', {
            'email': 'same@example.com', 'password': 'Strong-Password-2026!',
        }, format='json')
        self.assertEqual(duplicate.status_code, 400)

        invalid = self.client.post('/api/auth/register/', {
            'email': 'not-an-email', 'password': '123',
        }, format='json')
        self.assertEqual(invalid.status_code, 400)

    def test_invalid_login_does_not_reveal_account(self):
        response = self.client.post('/api/auth/login/', {
            'email': 'missing@example.com', 'password': 'Wrong-password!',
        }, format='json')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data['error'], 'Invalid credentials.')

    @patch('google.oauth2.id_token.verify_oauth2_token')
    def test_google_valid_identity_creates_account(self, verify):
        verify.return_value = {
            'email': 'google@example.com', 'email_verified': True,
            'given_name': 'Google', 'family_name': 'User',
        }
        from django.test import override_settings
        with override_settings(GOOGLE_OAUTH_CLIENT_ID='test-client-id'):
            response = self.client.post('/api/auth/google/', {
                'credential': 'valid-google-token',
            }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(email='google@example.com').exists())

    @patch('google.oauth2.id_token.verify_oauth2_token')
    def test_google_rejects_unverified_or_invalid_identity(self, verify):
        from django.test import override_settings
        verify.side_effect = ValueError('invalid')
        with override_settings(GOOGLE_OAUTH_CLIENT_ID='test-client-id'):
            invalid = self.client.post('/api/auth/google/', {'credential': 'bad'}, format='json')
        self.assertEqual(invalid.status_code, 401)

        verify.side_effect = None
        verify.return_value = {'email': 'unknown@example.com', 'email_verified': False}
        with override_settings(GOOGLE_OAUTH_CLIENT_ID='test-client-id'):
            unverified = self.client.post('/api/auth/google/', {'credential': 'token'}, format='json')
        self.assertEqual(unverified.status_code, 400)
