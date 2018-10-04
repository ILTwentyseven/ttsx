from django.urls import path, re_path
from user.views import RegisterView, ActiveView, LoginView, LogoutView, UserInfoView, UserOrderView, UserSiteView
from django.contrib.auth.decorators import login_required  # 登录页面后的跳转(只能用与Django内置认证系统。有login)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),  # 注册页面
    re_path(r'^active/(?P<token>.*$)', ActiveView.as_view(), name='active'),  # 用户激活页面
    path('login/', LoginView.as_view(), name='login'),  # 登录页面
    path('logout/', LogoutView.as_view(), name='logout'), # 注销登录

    # re_path(r'^$', login_required(UserInfoView.as_view()), name='info'),  # 用户信息页面
    # path('order/', login_required(UserOrderView.as_view()), name='order'),  # 用户订单页面
    # path('site/', login_required(UserSiteView.as_view()), name='site'),  # 用户地址页面
    re_path(r'^$', UserInfoView.as_view(), name='info'),  # 用户信息页面
    path('order/', UserOrderView.as_view(), name='order'),  # 用户订单页面
    path('site/', UserSiteView.as_view(), name='site'),  # 用户地址页面
]