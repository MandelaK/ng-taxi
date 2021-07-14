import pytest
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from taxi.routing import application


TEST_CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

PASSWORD = 'P@Swso9ds&'


@database_sync_to_async
def create_user(username, password=PASSWORD):
    user = get_user_model().objects.create_user(
        username=username, password=password)

    access = AccessToken.for_user(user)
    return user, access


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
        assert communicator.disconnect()

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

    async def test_can_send_and_receive_broadcast_messages(self, settings):
        """
        Users can send broadcast messages
        """
        settings.CHANNEL_LAYERS = TEST_CHANNEL_LAYERS

        _, access = await create_user(
            'test.user@example.com',
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
        await channel_layer.group_send('test', message=message)

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
