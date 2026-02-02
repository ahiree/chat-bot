# urls.py
from django.urls import path
from .views import LoginAPIView,SendOTPAPIView,VerifyOTPAPIView,CreditMoneyAPIView,DebitMoneyAPIView,BalanceAPIView

urlpatterns = [
    path('send-otp/', SendOTPAPIView.as_view()),
    path('verify-otp/', VerifyOTPAPIView.as_view()),
    path('login/', LoginAPIView.as_view()),
    path("credit/", CreditMoneyAPIView.as_view()),
    path("debit/", DebitMoneyAPIView.as_view()),
    path("balance/", BalanceAPIView.as_view()),
]

