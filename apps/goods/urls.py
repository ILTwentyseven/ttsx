from django.urls import path, re_path
from goods.views import IndexView
from apps.goods import views

urlpatterns = [
    path('index/', IndexView.as_view(), name='index'),  # 商品首页

]