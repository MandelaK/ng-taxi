import base64
import json
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.http import response as DjangoResponse
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase


from trips.models import Trip


PASSWORD = "pASSw0rd!"
DUPLICATE_USER_ERROR_MESSAGE = 'A user with that username already exists.'
FIELD_REQUIRED_ERROR_MESSAGE = 'This field is required.'
NO_ACTIVE_ACCOUNT_ERROR_MESSAGE = 'No active account found with the given credentials'


def create_user(username: str = "user@example.com", password: str = PASSWORD, first_name: str = "test", last_name: str = "user", group_name='rider'):
    group, _ = Group.objects.get_or_create(name=group_name)

    user = get_user_model().objects.create_user(
        username=username,
        first_name=first_name,
        last_name=last_name,
        password=password
    )

    user.groups.add(group)
    user.save()

    return user


class AuthenticationTest(APITestCase):
    def test_user_can_sign_up(self) -> None:
        """
        Users should be able to sign up when they provide accurate credentials
        """
        response: DjangoResponse.HttpResponse = self.client.post(reverse('sign_up'), data={
            'username': 'user@example.com',
            'first_name': 'test',
            'last_name': 'user',
            'password1': PASSWORD,
            'password2': PASSWORD,
            'group': 'rider'
        })

        user = get_user_model().objects.last()

        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertEqual(response.data['id'], user.id)
        self.assertEqual(response.data['username'], user.username)
        self.assertEqual(response.data['first_name'], user.first_name)
        self.assertEqual(response.data['last_name'], user.last_name)
        self.assertEqual(response.data['group'], user.group)

    def test_user_cannot_sign_up_with_duplicate_username(self):
        """
        A user should not be able to sign up if the username is already taken
        """
        create_user()

        response: DjangoResponse.HttpResponse = self.client.post(reverse('sign_up'), data={
            'username': 'user@example.com',
            'first_name': 'test',
            'last_name': 'user',
            'password1': PASSWORD,
            'password2': PASSWORD,
            'group': 'rider'
        })

        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertIsNotNone(response.data.get('username'))
        self.assertEqual(str(response.data.get('username')[
                         0]), DUPLICATE_USER_ERROR_MESSAGE)
        self.assertIsNone(response.data.get('id'))
        self.assertIsNone(response.data.get('first_name'))
        self.assertIsNone(response.data.get('last_name'))

    def test_user_must_provide_username_to_register(self):
        """
        A user must provide a username in order to sign up
        """
        response: DjangoResponse.HttpResponse = self.client.post(reverse('sign_up'), data={
            'first_name': 'test',
            'last_name': 'user',
            'password1': PASSWORD,
            'password2': PASSWORD,
            'group': 'rider'
        })

        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertIsNotNone(response.data.get('username'))
        self.assertEqual(str(response.data.get('username')[
                         0]), FIELD_REQUIRED_ERROR_MESSAGE)
        self.assertIsNone(response.data.get('id'))
        self.assertIsNone(response.data.get('first_name'))
        self.assertIsNone(response.data.get('last_name'))

    def test_user_must_provide_matching_passwords_to_register(self):
        """
        A user must provide matching passwords in order to sign up
        """
        response: DjangoResponse.HttpResponse = self.client.post(reverse('sign_up'), data={
            'username': 'test@example.com',
            'first_name': 'test',
            'last_name': 'user',
            'password1': PASSWORD,
            'password2': f'{PASSWORD}32',
            'group': 'rider'
        })

        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertIsNone(response.data.get('username'))
        self.assertIsNotNone(response.data.get('password1'))
        self.assertEqual(str(response.data.get('password1')[
                         0]), 'Passwords must match.')
        self.assertIsNone(response.data.get('id'))
        self.assertIsNone(response.data.get('first_name'))
        self.assertIsNone(response.data.get('last_name'))

    def test_user_can_log_in(self) -> None:
        """
        Users should be able to log in when they provide accurate credentials
        """
        user = create_user()
        response: DjangoResponse.HttpResponse = self.client.post(reverse('log_in'), data={
            'username': user.username,
            'password': PASSWORD
        })

        # Parse payload data from access token
        access: str = response.data['access']
        header, payload, signature = access.split('.')
        decoded_payload: bytes = base64.b64decode(f'{payload}==')
        payload_data = json.loads(decoded_payload)

        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertIsNotNone(response.data['refresh'])
        self.assertEqual(payload_data['id'], user.id)
        self.assertEqual(payload_data['username'], user.username)
        self.assertEqual(payload_data['first_name'], user.first_name)
        self.assertEqual(payload_data['last_name'], user.last_name)

    def test_user_cannot_log_in_with_non_existent_username(self):
        """
        A user should not be able to log in if they provide a username that does not exist
        """
        response: DjangoResponse.HttpResponse = self.client.post(reverse('log_in'), data={
            'username': 'veryfakeusername',
            'password': PASSWORD
        })

        self.assertEqual(status.HTTP_401_UNAUTHORIZED, response.status_code)
        self.assertIsNone(response.data.get('refresh'))
        self.assertIsNone(response.data.get('access'))
        self.assertEqual(response.data.get('detail').code, 'no_active_account')
        self.assertEqual(str(response.data.get('detail')),
                         NO_ACTIVE_ACCOUNT_ERROR_MESSAGE)

    def test_user_cannot_log_in_with_incorrect_password(self):
        """
        Users must provide correct password to log in
        """
        user = create_user()

        response: DjangoResponse.HttpResponse = self.client.post(reverse('log_in'), data={
            'username': user.username,
            'password': 'clearlyfakepassword'
        })

        self.assertEqual(status.HTTP_401_UNAUTHORIZED, response.status_code)
        self.assertIsNone(response.data.get('refresh'))
        self.assertIsNone(response.data.get('access'))
        self.assertEqual(response.data.get('detail').code, 'no_active_account')
        self.assertEqual(str(response.data.get('detail')),
                         NO_ACTIVE_ACCOUNT_ERROR_MESSAGE)


class HttpTripTest(APITestCase):
    def setUp(self):
        self.user = create_user()
        self.client.login(username=self.user.username, password=PASSWORD)

    def test_user_can_list_trips(self):
        """
        Users should be able to view a list of their trips
        """

        trips = [
            Trip.objects.create(pick_up_address="A",
                                drop_off_address="B", rider=self.user),
            Trip.objects.create(pick_up_address="C",
                                drop_off_address="D", rider=self.user),
            # Create a trip that is not associated to any rider, then we can test whether
            # the rider can view it
            Trip.objects.create(pick_up_address="D",
                                drop_off_address="E")

        ]

        response = self.client.get(
            reverse('trip:trip_list'))

        self.assertEqual(status.HTTP_200_OK, response.status_code)

        # We expecte the rider to only see the first two trips, as the third
        # trip is ont associated to them
        expected_trip_ids = [str(trip.id) for trip in trips[0:2]]
        actual_trip_ids = [trip.get('id') for trip in response.data]

        self.assertCountEqual(expected_trip_ids, actual_trip_ids)

    def test_user_can_retrieve_trip_by_id(self):
        """
        A user should be able to retrieve a single trip by its ID
        """

        trip = Trip.objects.create(
            pick_up_address="A", drop_off_address="B", rider=self.user)
        response = self.client.get(trip.get_absolute_url(
        ))

        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(str(trip.id), response.data.get('id'))

    def test_user_cannot_retrieve_trip_that_does_not_exist(self):
        """
        A user should not be able to retrieve a single trip by its ID, if
        the trip ID does not exist
        """
        response = self.client.get(reverse('trip:trip_detail', kwargs={
            'trip_id': str(uuid.uuid4())
        }))

        self.assertEqual(status.HTTP_404_NOT_FOUND, response.status_code)
        self.assertIsNone(response.data.get('id'))

    def test_that_rider_cannot_view_trip_that_is_not_theirs(self):
        """
        A rider should not be able to view a trip that they did not request
        """
        trip = Trip.objects.create(
            pick_up_address="A", drop_off_address="B")
        response = self.client.get(trip.get_absolute_url(
        ))

        self.assertEqual(status.HTTP_404_NOT_FOUND, response.status_code)
        self.assertIsNone(response.data.get('id'))
