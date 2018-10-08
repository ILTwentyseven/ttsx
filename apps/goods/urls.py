from django.urls import path, re_path
from goods.views import IndexView, DetailView, ListView
from apps.goods import views

urlpatterns = [
    path('index/', IndexView.as_view(), name='index'),  # 商品首页
    re_path(r'^goods/(?P<goods_id>\d+)$', DetailView.as_view(), name='detail'),  # 详情页
    re_path(r'^list/(?P<type_id>\d+)/(?P<page>\d+)$', ListView.as_view(), name='list'),  # 列表页
]
