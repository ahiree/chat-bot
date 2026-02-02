# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import LoginSerializer



class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if not serializer.is_valid():
            print("LOGIN ERROR:", serializer.errors)  # 👈 IMPORTANT
            return Response(serializer.errors, status=400)

        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        })


from rest_framework.views import APIView
from rest_framework.response import Response
from .models import OTP, User

class SendOTPAPIView(APIView):
    def post(self, request):
        phone = request.data.get("phone_number")
        email = request.data.get("email")
        full_name = request.data.get("full_name")

        if User.objects.filter(phone_number=phone).exists():
            return Response({"error": "Phone already registered"}, status=400)

        otp_code = OTP.generate_otp()

        OTP.objects.create(phone_number=phone, otp=otp_code)

        # TODO: Integrate SMS gateway here
        print(f"OTP for {phone}: {otp_code}")

        return Response({"message": "OTP sent successfully"})


class VerifyOTPAPIView(APIView):
    def post(self, request):
        phone = request.data.get("phone_number")
        otp = request.data.get("otp")
        email = request.data.get("email")
        full_name = request.data.get("full_name")
        password = request.data.get("password")

        try:
            otp_obj = OTP.objects.filter(phone_number=phone, otp=otp, is_verified=False).latest('created_at')
        except OTP.DoesNotExist:
            return Response({"error": "Invalid OTP"}, status=400)

        if otp_obj.is_expired():
            return Response({"error": "OTP expired"}, status=400)

        otp_obj.is_verified = True
        otp_obj.save()

        user = User.objects.create_user(
            email=email,
            password=password
        )
        user.phone_number = phone
        user.full_name = full_name
        user.is_phone_verified = True
        user.save()

        return Response({"message": "Registration successful"})

from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken

class LoginAPIView(APIView):
    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(email=email, password=password)

        if not user:
            return Response({"error": "Invalid credentials"}, status=401)

        refresh = RefreshToken.for_user(user)

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "full_name": user.full_name
        })


from django.db import transaction
from django.db.models import F
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Account, Transaction
from .serializers import AmountSerializer

class CreditMoneyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = AmountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data["amount"]

        account, _ = Account.objects.select_for_update().get_or_create(
            user=request.user
        )

        account.balance = F("balance") + amount
        account.save()
        account.refresh_from_db()  # 🔑 REQUIRED

        Transaction.objects.create(
            account=account,
            amount=amount,
            transaction_type=Transaction.CREDIT
        )

        return Response(
            {
                "message": "Amount credited successfully",
                "balance": str(account.balance)
            },
            status=status.HTTP_200_OK
        )


class DebitMoneyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = AmountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data["amount"]

        account = Account.objects.select_for_update().get(user=request.user)

        if account.balance < amount:
            return Response(
                {"error": "Insufficient balance"},
                status=status.HTTP_400_BAD_REQUEST
            )

        account.balance = F("balance") - amount
        account.save()
        account.refresh_from_db()  # 🔑 REQUIRED

        Transaction.objects.create(
            account=account,
            amount=amount,
            transaction_type=Transaction.DEBIT
        )

        return Response(
            {
                "message": "Amount debited successfully",
                "balance": str(account.balance)
            },
            status=status.HTTP_200_OK
        )


class BalanceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        account, _ = Account.objects.get_or_create(user=request.user)

        return Response(
            {
                "balance": str(account.balance)
            },
            status=status.HTTP_200_OK
        )