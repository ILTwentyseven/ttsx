from django.urls import path, re_path
from cart.views import CartAddView, CartInfoView, CartUpdateView

urlpatterns = [
    path('add/', CartAddView.as_view(), name='add'),  # 购物车添加
    re_path(r'^$', CartInfoView.as_view(), name='show'),  # 购物车页面
    re_path(r'^update$', CartUpdateView.as_view(), name='update'),  # 购物车更新页面


]