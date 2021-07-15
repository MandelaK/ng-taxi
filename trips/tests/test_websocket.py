import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from taxi.routing import application
from trips.models import Trip


TEST_CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

PASSWORD = 'P@Swso9ds&'


@database_sync_to_async
def create_user(username, password=PASSWORD, group='rider'):
    user = get_user_model().objects.create_user(
        username=username, password=password)

    # create user group
    user_group, _ = Group.objects.get_or_create(name=group)
    user.groups.add(user_group)
    user.save()

    access = AccessToken.for_user(user)
    return user, access


@database_sync_to_async
def create_trip(
    pick_up_address="123 Test Street",
    drop_off_address="456 Test Street",
    status="REQUESTED",
    rider=None,
    driver=None
):
    return Trip.objects.create(
        pick_up_address=pick_up_address,
        drop_off_address=drop_off_address,
        status=status,
        rider=rider,
        driver=driver
    )


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestWebsocket:
    async def test_can_connect_to_server(self, settings):
        """
        Authenticated users should be able to connect to the server
        """
        settings.CHANNEL_LAYERS = TEST_CHANNEL_LAYERS

        _, access = await create_user(
            'test.user@example.com',
        )

        communicator = WebsocketCommunicator(
            application=application,
            path=f'/taxi/?token={access}'
        )

        connected, _ = await communicator.connect()

        assert connected is True

        disconnected = await communicator.disconnect()
        assert disconnected is None

    async def test_can_send_and_receive_messages(self, settings):
        """
        Users can send and receive messages
        """
        settings.CHANNEL_LAYERS = TEST_CHANNEL_LAYERS

        _, access = await create_user(
            'test.user@example.com',
        )

        communicator = WebsocketCommunicator(
            application=application, path=f"/taxi/?token={access}"
        )

        connected, _ = await communicator.connect()

        assert connected is True

        message = {
            'type': 'echo.message',
            'data': 'This is a test message',
        }

        await communicator.send_json_to(message)
        response = await communicator.receive_json_from()
        assert response == message
        await communicator.disconnect()

    async def test_cannot_connect_to_websocket(self, settings):
        """
        Unauthenticated users should not be able to connect to the server
        """
        settings.CHANNEL_LAYERS = TEST_CHANNEL_LAYERS
        communicator = WebsocketCommunicator(
            application=application,
            path='/taxi/'
        )

        connected, _ = await communicator.connect()

        assert connected is False
        await communicator.disconnect()

    async def test_join_driver_pool(self, settings):
        """
        Drivers should be able to join the driver pool and receive broadcasts
        """
        settings.CHANNEL_LAYERS = TEST_CHANNEL_LAYERS

        _, access = await create_user(
            'test.user@example.com', PASSWORD, 'driver'
        )

        communicator = WebsocketCommunicator(
            application=application,
            path=f"/taxi/?token={access}"
        )

        connected, _ = await communicator.connect()

        assert connected is True

        message = {
            'type': 'echo.message',
            'data': 'This is a test message'
        }

        channel_layer = get_channel_layer()
        await channel_layer.group_send('drivers', message=message)
        response = await communicator.receive_json_from()
        assert response == message

        await communicator.disconnect()

    async def test_request_trip(self, settings):
        """
        Users should be able to request a trip
        """
        settings.CHANNEL_LAYERS = TEST_CHANNEL_LAYERS

        user, access = await create_user(
            'test@user.example.com', PASSWORD, 'rider'
        )

        communicator = WebsocketCommunicator(
            application=application,
            path=f"/taxi/?token={access}"
        )

        connected, _ = await communicator.connect()

        assert connected is True
        await communicator.send_json_to({
            'type': 'create.trip',
            'data': {
                'pick_up_address': 'MX',
                'drop_off_address': 'GY',
                'rider': user.id
            },
        })

        response = await communicator.receive_json_from()

        response_data = response.get('data')
        assert response_data['id'] is not None
        assert response_data['pick_up_address'] == 'MX'
        assert response_data['drop_off_address'] == 'GY'
        assert response_data['status'] == 'REQUESTED'
        assert response_data['rider']['username'] == user.username
        assert response_data['driver'] is None

        await communicator.disconnect()

    async def test_driver_alerted_on_request(self, settings):
        """
        Drivers should be alerted whenever a user requests a trip
        """
        settings.CHANNEL_LAYERS = TEST_CHANNEL_LAYERS

        # Listen to the 'drivers' group test channel
        channel_layer = get_channel_layer()
        await channel_layer.group_add(
            group='drivers',
            channel='test_channel'
        )

        user, access = await create_user(
            'user@example.com', PASSWORD, 'rider'
        )

        communicator = WebsocketCommunicator(
            application=application,
            path=f"/taxi/?token={access}"
        )

        connected, _ = await communicator.connect()

        assert connected is True

        # Request a trip
        await communicator.send_json_to({
            'type': 'create.trip',
            'data': {
                'pick_up_address': 'NY',
                'drop_off_address': 'RS',
                'rider': user.id,
            },
        })

        # Receive JSON message from server on test channel.
        response = await channel_layer.receive('test_channel')
        response_data = response.get('data')

        assert response_data['id'] is not None
        assert response_data['rider']['username'] == user.username
        assert response_data['driver'] is None

        await communicator.disconnect()

    async def test_create_trip_group(self, settings):
        """
        A trip group should be created for a rider
        """
        settings.CHANNEL_LAYERS = TEST_CHANNEL_LAYERS

        user, access = await create_user(
            'user@example.com', PASSWORD, 'rider'
        )

        communicator = WebsocketCommunicator(
            application=application,
            path=f"/taxi/?token={access}"
        )

        connected, _ = await communicator.connect()

        assert connected is True

        # Send a trip ride request
        await communicator.send_json_to({
            'type': 'create.trip',
            'data': {
                'pick_up_address': 'MX',
                'drop_off_address': 'TY',
                'rider': user.id,
            },
        })

        response = await communicator.receive_json_from()
        response_data = response.get('data')

        # Send a message to the trip group
        message = {
            'type': 'echo.message',
            'data': 'This is a test message'
        }

        channel_layer = get_channel_layer()

        await channel_layer.group_send(response_data['id'], message=message)

        # Rider receives message
        rider_response = await communicator.receive_json_from()

        assert rider_response == message

        await communicator.disconnect()

    async def test_join_trip_group_on_connect(self, settings):
        """
        Whenever a user connects to the server, the should automatically join
        trip groups for their currently active trips
        """
        settings.CHANNEL_LAYERS = TEST_CHANNEL_LAYERS

        user, access = await create_user(
            'test@example.com', PASSWORD, 'rider'
        )

        trip = await create_trip(rider=user)

        communicator = WebsocketCommunicator(
            application=application,
            path=f"/taxi/?token={access}"
        )

        connected, _ = await communicator.connect()

        assert connected is True

        # Send a message to the trip group
        message = {
            'type': 'echo.message',
            'data': 'This is a test message.',
        }

        channel_layer = get_channel_layer()
        await channel_layer.group_send(f"{trip.id}", message=message)

        # Rider receives message
        response = await communicator.receive_json_from()

        assert response == message

        await communicator.disconnect()

    async def test_driver_can_accept_trip(self, settings):
        """
        A driver should be able to accept a requested trip
        """
        settings.CHANNEL_LAYERS = TEST_CHANNEL_LAYERS

        rider, _ = await create_user(
            'user@example.com', PASSWORD, 'rider'
        )

        trip = await create_trip(rider=rider)
        trip_id = f"{trip.id}"

        # Listen to messages as rider
        channel_layer = get_channel_layer()
        await channel_layer.group_add(
            group=trip_id,
            channel='test_channel'
        )

        # Update trip as driver
        driver, access = await create_user(
            'driver@example.com', PASSWORD, 'driver'
        )

        communicator = WebsocketCommunicator(
            application=application,
            path=f"/taxi/?token={access}"
        )

        connected, _ = await communicator.connect()

        assert connected is True

        message = {
            'type': 'update.trip',
            'data': {
                'id': trip_id,
                'pick_up_address': trip.pick_up_address,
                'drop_off_address': trip.drop_off_address,
                'status': Trip.IN_PROGRESS,
                'driver': driver.id,
            },
        }

        await communicator.send_json_to(message)

        # Rider receives message
        response = await channel_layer.receive('test_channel')
        response_data = response.get('data')

        assert response_data['id'] == trip_id
        assert response_data['rider']['username'] == rider.username
        assert response_data['driver']['username'] == driver.username
        assert response_data['status'] == Trip.IN_PROGRESS

        await communicator.disconnect()

    async def test_driver_join_trip_group_on_connect(self, settings):
        """
        Drivers should join their trip group when they connect to the server
        """
        settings.CHANNEL_LAYERS = TEST_CHANNEL_LAYERS

        user, access = await create_user(
            'driver@example.com', PASSWORD, 'driver'
        )

        trip = await create_trip(driver=user)

        communicator = WebsocketCommunicator(
            application=application,
            path=f"/taxi/?token={access}"
        )

        connected, _ = await communicator.connect()

        assert connected is True

        # Send a message to the trip group
        message = {
            'type': 'echo.message',
            'data': 'This is a test message',
        }

        channel_layer = get_channel_layer()
        await channel_layer.group_send(f'{trip.id}', message=message)

        # Rider receives message
        response = await communicator.receive_json_from()

        assert response == message

        await communicator.disconnect()
