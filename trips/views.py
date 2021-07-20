from django.contrib.auth import get_user_model
from django.db.models.query_utils import Q
from rest_framework import generics, viewsets, permissions
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import TripSerializer, UserSerializer, LoginSerializer
from .models import Trip


class SignUpView(generics.CreateAPIView):
    queryset = get_user_model().objects.all()
    serializer_class = UserSerializer


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer


class TripView(viewsets.ReadOnlyModelViewSet):
    lookup_field = 'id'
    lookup_url_kwarg = 'trip_id'

    permission_classes = (permissions.IsAuthenticated,)
    queryset = Trip.objects.all()
    serializer_class = TripSerializer

    def get_queryset(self):
        """
        Depending on the user making the request, we return a different queryset
        """
        user = self.request.user

        if user.group == 'driver':
            # Drivers only see requested trips or trips where they are the driver
            return Trip.objects.filter(
                Q(status=Trip.REQUESTED) | Q(driver=user)
            )

        if user.group == 'rider':
            # Riders only see their own trips
            return Trip.objects.filter(rider=user)

        return Trip.objects.none()
