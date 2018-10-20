from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.generic import View
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse

from user.models import User, Address
from goods.models import GoodsSKU
from order.models import OrderInfo, OrderGoods

from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired
from django.conf import settings
from utils.mixin import LoginRequiredMixin
from django.http import HttpResponse
from django.core.mail import send_mail
from celery_tasks.tasks import send_register_active_email
from django_redis import get_redis_connection
from django.core.paginator import Paginator
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
                    response.set_cookie('username', username.encode('utf8'), max_age=7*24*3600)
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
    def get(self, request, page):
        #  获取用户登录信息
        user = request.user
        # 获取用户的订单信息
        orders = OrderInfo.objects.filter(user=user).order_by('-create_time')
        # 遍历获取到的订单信息
        for order in orders:
            # 根据order_id 获取商品的信息
            order_skus = OrderGoods.objects.filter(order_id=order.order_id)
            # 遍历order_skus 计算商品的小计
            for order_sku in order_skus:
                # 计算小计
                amount = order_sku.price*order_sku.count
                # 动态给order_sku增加属性amount 保存订单商品的小计
                order_sku.amount = amount
            # 动态给order增加属性 保存订单状态标题
            order.status_name = OrderInfo.ORDER_STATUS[order.order_status]
            # 动态给order增加属性 保存订单商品的信息
            order.order_skus = order_skus
        # 分页
        paginator = Paginator(orders, 1)
        # 获取第page页的内容
        try:
            page = int(page)
        except Exception as e:
            page = 1
        if page > paginator.num_pages:
            page = 1
        # 获取当前page页的内容
        order_page = paginator.page(page)
        # 页码控制，最多显示五页
        # 总页数小于五页。显示全部页码
        # 如果当前页式前三页显示1-5页
        # 如果当前页式后三页显示最后五页
        # 其他情况，显示当前页的前两页，当前页和后两页
        num_pages = paginator.num_pages
        if num_pages < 5:
            pages = range(1, num_pages + 1)
        elif num_pages <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages - 4, num_pages + 1)
        else:
            pages = range(page - 2, page + 3)

        # 组织模板上下文
        context = {'pages': pages,
                   'order_page': order_page,
                   'page': 'order'}

        return render(request, 'user_center_order.html', context)

    def post(self, request):
        user = request.user
        # 接受数据
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')
        # 数据校验
        # 校验是否登录状态
        if not user.is_authenticated:
            # 用户未登录
            return JsonResponse({'ret': 0, 'errmsg': '用户未登录'})
        # 校验数据是否完整
        if not all([sku_id, count]):
            # 数据不完整
            return JsonResponse({'ret': 1, 'errmsg': '数据不完整'})
        # 校验添加的商品数量
        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({'ret': 2, 'errmsg': '商品数目错误'})
        # 校验商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'ret': 3, 'errmsg': '商品不存在'})
        # 添加购物车记录
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        # 获取购物车中的值
        cart_count = conn.hget(cart_key, sku_id)
        # 判断接收的值
        if cart_count:
            count += int(cart_count)
        # 判断库存
        if count > sku.stock:
            return JsonResponse({'ret': 4, 'errmsg': '商品库存不足'})
        # 添加记录。使用哈希存储, 有数据则更新。无数据则添加
        conn.hset(cart_key, sku_id, count)
        # 计算购物车中的条目数
        total_count = conn.hlen(cart_key)
        # 返回应答
        return JsonResponse({'ret': 5, 'total_count': total_count, 'message': '添加成功'})


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

