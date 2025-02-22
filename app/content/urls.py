from django.urls import path

from . import views

urlpatterns = [
    path(
        "create-contract/", views.ContractCreateView.as_view(), name="create-contract"
    ),
    path(
        "accept-contract/",
        views.AcceptContractAPIView.as_view(),
        name="accept-contract",
    ),
]
