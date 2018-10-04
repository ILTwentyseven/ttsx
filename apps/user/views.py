from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.generic import View
from django.contrib.auth import authenticate, login, logout
from user.models import User, Address
from goods.models import GoodsSKU
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired
from django.conf import settings
from utils.mixin import LoginRequiredMixin
from django.http import HttpResponse
from django.core.mail import send_mail
from celery_tasks.tasks import send_register_active_email
from django_redis import get_redis_connection
import re
# Create your views here.


# user/register
class RegisterView(View):
    """注册类"""
    def get(self, request):
        """显示注册页面"""
        return render(request, 'register.html')

    # 注册处理
    def post(self, request):
        """注册处理"""
        # 接受数据
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')
        # 进行数据校验
        if not all([username, password, email]):
            return render(request, 'register.html', {'errmsg': '数据信息不完整'})
        # 邮箱验证
        if not re.match("^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$", email):
            return render(request, 'register.html', {'errmsg': '邮箱格式不正确'})
        # 协议校验
        if allow != 'on':
            return render(request, 'register.html', {'errmsg': '请同意协议'})
        # 数据注册
        user = User.objects.create_user(username, email, password)
        user.is_active = 0
        user.save()
        # 生成激活链接ID
        serializer = Serializer(settings.SECRET_KEY, 3600)
        info = {'confirm': user.id}
        token = serializer.dumps(info)
        token = token.decode()
        # 发送邮件
        send_register_active_email.delay(email, username, token)
        # 返回应答。跳转到商品首页
        return redirect(reverse('goods:index'))


class ActiveView(View):
    """用户激活"""
    # 进行解密
    def get(self, request, token):
        serializer = Serializer(settings.SECRET_KEY, 3600)
        try:
            # 解密，获得用户信息
            info = serializer.loads(token)
            user_id = info['confirm']
            user = User.objects.get(id=user_id)
            # 将用户激活
            user.is_active = 1
            user.save()
            # 转到登录页面
            return redirect(reverse('user:login'))
        except SignatureExpired as e:
            return HttpResponse('激活链接已过期')


class LoginView(View):
    """登录页面"""
    def get(self, request):
        # 判断用户是否记住了用户名
        if 'username' in request.COOKIES:
            username = request.COOKIES.get('username')
            checked = 'checked'
        else:
            username = ''
            checked = ''

        return render(request, 'login.html', {'username': username, 'checked': checked})

    def post(self, request):
        # 接受数据
        username = request.POST.get('username')
        password = request.POST.get('pwd')
        # 判断数据
        if not all([username, password]):
            return render(request, 'login.html', {'errmsg': '用户名或密码不能为空'})
        # 判断用户名和密码是否正确
        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                # 获取登录后所要跳转的地址
                next_url = request.GET.get('next', reverse('goods:index'))
                # 用户已激活
                response = redirect(next_url)
                remember = request.POST.get('remember')
                if remember == 'on':
                    response.set_cookie('username', username, max_age=7*24*3600)
                else:
                    response.delete_cookie('username')
                return response
                # 设置session信息
            else:
                # 用户未激活(最好设置为为用户发送一封激活邮件）
                return render(request, 'login.html', {'errmsg': '用户未激活'})
        else:
            # 用户名或密码不正确
            return render(request, 'login.html', {'errmsg': '用户名或密码不正确'})


# /user/logout
class LogoutView(View):
    '''退出登录'''
    def get(self, request):
        '''退出登录'''
        # 清除用户的session信息
        logout(request)
        # 跳转到首页
        return redirect(reverse('goods:index'))


# user/info
class UserInfoView(LoginRequiredMixin, View):
    """用户信息界面"""
    def get(self, request):
        # 获取登录信息
        user = request.user
        # 获取用户的个人信息
        address = Address.objects.get_default_address(user)
        # 获取用户的历史浏览记录
        con = get_redis_connection('default')
        history_key = 'history_%d' % user.id
        # 从历史浏览记录中查询商品ID
        sku_ids = con.lrange(history_key, 0, 4)
        # 将查询到的ID进行遍历排序
        goods_li = []
        for id in sku_ids:
            goods = GoodsSKU.objects.get(id=id)
            goods_li.append(goods)
        # 组织上下文
        context = {'page': 'info',
                   'address': address,
                   'goods_li': goods_li}

        return render(request, 'user_center_info.html', context)


# user/order
class UserOrderView(LoginRequiredMixin, View):
    """用户订单界面"""
    def get(self, request):
        return render(request, 'user_center_order.html', {'page': 'order'})


# user/site
class UserSiteView(LoginRequiredMixin, View):
    """用户地址界面"""
    def get(self, request):
        # 获取登录对象的信息
        user = request.user
        # try:
        #     address = Address.objects.get(user=user, is_default=True)
        # except Address.DoesNotExist:
        #     # 不存在默认收获地址
        #     address = None
        address = Address.objects.get_default_address(user)
        return render(request, 'user_center_site.html', {'page': 'site', 'address':address})

    # 接受数据
    def post(self, request):

        # 接受传递的数据
        receiver = request.POST.get('receiver')
        addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code')
        phone = request.POST.get('phone')
        # 判断信息是否完整
        if not all([receiver, addr, phone]):
            return render(request, 'user_center_site.html', {'errmsg': '数据不完整'})
        # 判断电话号码是否正确
        if not re.match('^(13\d|14[5|7]|15\d|166|17[3|6|7]|18\d)\d{8}$', phone):
            return render(request, 'user_center_site.html', {'errmsg': '电话号码不正确'})
        # 将数据存入数据库
        # 获取登录对象的信息
        user = request.user
        # try:
        #     address = Address.objects.get(user=user, is_default=True)
        # except Address.DoesNotExist:
        #     # 不存在默认收获地址
        #     address = None
        address = Address.objects.get_default_address(user)
        if address:
            is_default = False
        else:
            is_default = True
        Address.objects.create(user=user,
                               receiver=receiver,
                               addr=addr,
                               zip_code=zip_code,
                               phone=phone,
                               is_default=is_default)
        # 返回应答
        return redirect(reverse('user:site'))

