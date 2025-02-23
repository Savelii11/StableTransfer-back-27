from django.urls import path

from . import views

urlpatterns = [
    path(
        "create-contract/", views.ContractCreateView.as_view(), name="create-contract"
    ),
    path(
        "accept-contract/<int:contract_id>/",
        views.AcceptContractAPIView.as_view(),
        name="accept-contract",
    ),
    path(
        "contract-raise-dispute/<int:contract_id>/",
        views.ContractRaiseDispute.as_view(),
        name="contract-raise-dispute",
    ),
    path("contracts/", views.GetContractsAPIView.as_view(), name="get-contract"),
    path(
        "contracts/<int:contract_id>/",
        views.GetContractsAPIView.as_view(),
        name="get-specific-contract",
    ),
]
