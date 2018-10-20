from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.urls import reverse
from django.views.generic import View
from utils.mixin import LoginRequiredMixin
from django_redis import get_redis_connection
from django.db import transaction
from alipay import AliPay
from django.conf import settings
from datetime import datetime

from goods.models import GoodsSKU
from user.models import Address
from order.models import OrderInfo, OrderGoods

import os
# Create your views here.


# order/palce
class OrderPlaceView(LoginRequiredMixin, View):
    """订单页面显示模块"""
    def post(self, request):
        """订单页面显示"""
        # 当前用户查询
        user = request.user
        # 获取参数sku_ids
        sku_ids = request.POST.getlist('sku_ids')
        # 校验藏书
        if not sku_ids:
            # 返回至购物车页面
            return redirect(reverse('cart:show'))
        # 链接redis
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        # 保存商品的总数目和价格
        skus = []
        total_count = 0
        total_price = 0
        # 遍历sku_ids 获取信息
        for sku_id in sku_ids:
            # 当前商品对应的信息
            sku = GoodsSKU.objects.get(id=sku_id)
            # 获取数量
            count = conn.hget(cart_key, sku_id)
            # 计算小计
            amount = sku.price*int(count)
            # 动态添加 数量和小计至sku
            sku.count = int(count)
            sku.amount = amount
            # 累计计算总价格和总数目
            total_count += int(count)
            total_price += amount
            # 添加sku到列表
            skus.append(sku)
        # 运费的添加 本该是一个表单 现在定死
        trans_pay = 10
        # 实际付款
        order_pay = total_price + trans_pay
        # 获取用户的地址
        addrs = Address.objects.filter(user=user)
        # 将sku_ids 转换为有一个逗号隔开的字符串
        sku_ids = ','.join(sku_ids)
        # 组织模板上下文
        context = {'skus': skus,
                   'total_count': total_count,
                   'total_price': total_price,
                   'trans_pay': trans_pay,
                   'order_pay': order_pay,
                   'addrs': addrs,
                   'sku_ids': sku_ids}
        # 上传
        return render(request, 'place_order.html', context)


# /order/commit 采用悲观锁
class OrderCommitView1(View):
    """订单创建"""
    @transaction.atomic
    def post(self, request):
        """订单创建"""
        # 用户是否登录
        user = request.user
        if not user.is_authenticated:
            # 用户未登录
            return JsonResponse({'ret': 0, 'errmsg': '用户未登录'})
        # 接收数据 需要接收 addr_id pay_method sku_ids
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')
        # 校验参数
        if not all([addr_id, pay_method, sku_ids]):
            # 信息不完整
            return JsonResponse({'ret': 1, 'errmsg': '信息部完整'})
        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'ret': 2, 'errmsg': '错误的支付方式'})
        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist as e:
            return JsonResponse({'ret': 3, 'errmsg': '无效的地址'})
        # todo: 创建订单核心业务
        # 组织参数
        # 订单id order_id 201810121404+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)
        # 运费 总数目总金额
        transit_price = 10
        total_count = 0
        total_price = 0
        # todo: 设置事务保存点
        save_id = transaction.savepoint()
        try:
            # todo: 向df_order_info 表中添加一条记录
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_count=total_count,
                                             total_price=total_price,
                                             transit_price=transit_price,)
            # todo: 用户的订单中有几个商品就要向df_order_goods 表中添加几条记录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                # 获取商品信息
                try:
                    sku = GoodsSKU.objects.select_for_update().get(id=sku_id)
                except GoodsSKU.DoesNotExist as e:
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'ret': 4, 'errmsg': '无效的商品'})
                # 获取商品的数量 redis中获取
                count = conn.hget(cart_key, sku_id)
                # todo: 判断商品的库存
                if int(count) > sku.stock:
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'ret': 7, 'errms': '商品库存不足'})
                # todo: 向df_order_goods表中添加记录
                OrderGoods.objects.create(order=order,
                                          sku=sku,
                                          count=count,
                                          price=sku.price)
                # todo: 更新商品的库存和销量
                sku.stock -= int(count)
                sku.sales += int(count)
                sku.save()
                # todo: 累计计算商品的总数量和总价格
                amount = sku.price*int(count)
                total_price += amount
                total_count += int(count)
            # todo: 更新订单表中的总数量和总价格
            order.total_price = total_price
            order.total_count = total_count
            order.save()

        except OrderInfo.DoesNotExist as e:
            return JsonResponse({'ret': 6, 'errmsg': '下单失败'})

        # todo: 清除购物车中对应的商品
        conn.hdel(cart_key, *sku_ids)
        # 返回应答
        return JsonResponse({'ret': 5, 'mssage': '下单成功'})


# /order/commit 采用乐观锁
class OrderCommitView(View):
    """订单创建"""
    @transaction.atomic
    def post(self, request):
        """订单创建"""
        # 用户是否登录
        user = request.user
        if not user.is_authenticated:
            # 用户未登录
            return JsonResponse({'ret': 0, 'errmsg': '用户未登录'})
        # 接收数据 需要接收 addr_id pay_method sku_ids
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')
        # 校验参数
        if not all([addr_id, pay_method, sku_ids]):
            # 信息不完整
            return JsonResponse({'ret': 1, 'errmsg': '信息部完整'})
        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'ret': 2, 'errmsg': '错误的支付方式'})
        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist as e:
            return JsonResponse({'ret': 3, 'errmsg': '无效的地址'})
        # todo: 创建订单核心业务
        # 组织参数
        # 订单id order_id 201810121404+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)
        # 运费 总数目总金额
        transit_price = 10
        total_count = 0
        total_price = 0
        # todo: 设置事务保存点
        save_id = transaction.savepoint()
        try:
            # todo: 向df_order_info 表中添加一条记录
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_count=total_count,
                                             total_price=total_price,
                                             transit_price=transit_price,)
            # todo: 用户的订单中有几个商品就要向df_order_goods 表中添加几条记录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                for i in range(3):
                    # 获取商品信息
                    try:
                        sku = GoodsSKU.objects.get(id=sku_id)
                    except GoodsSKU.DoesNotExist as e:
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'ret': 4, 'errmsg': '无效的商品'})
                    # 获取商品的数量 redis中获取
                    count = conn.hget(cart_key, sku_id)
                    # todo: 判断商品的库存
                    if int(count) > sku.stock:
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'ret': 7, 'errms': '商品库存不足'})

                    # todo: 更新商品的库存和销量
                    orgin_stock = sku.stock
                    new_sales = sku.sales + int(count)
                    new_stock = orgin_stock - int(count)
                    ret = GoodsSKU.objects.filter(id=sku_id, stock=orgin_stock).update(stock=new_stock, sales=new_sales)
                    if ret == 0:
                        if i == 2:
                            transaction.savepoint_rollback(save_id)
                            return JsonResponse({'ret': 8, 'errmsg': '下单失效'})
                        continue
                    # todo: 向df_order_goods表中添加记录
                    OrderGoods.objects.create(order=order,
                                              sku=sku,
                                              count=count,
                                              price=sku.price)

                    # todo: 累计计算商品的总数量和总价格
                    amount = sku.price*int(count)
                    total_price += amount
                    total_count += int(count)
                    # 跳出循环
                    break
            # todo: 更新订单表中的总数量和总价格
            order.total_price = total_price
            order.total_count = total_count
            order.save()

        except OrderInfo.DoesNotExist as e:
            return JsonResponse({'ret': 6, 'errmsg': '下单失败'})

        # todo: 清除购物车中对应的商品
        conn.hdel(cart_key, *sku_ids)
        # 返回应答
        return JsonResponse({'ret': 5, 'mssage': '下单成功'})


# /order/pay
class OrderPayView(View):
    """订单支付模块"""
    def post(self, request):
        """订单支付"""
        # 用户登录
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'ret': 0, 'errmsg': '用户未登录'})
        # 接受参数
        order_id = request.POST.get('order_id')
        # 校验参数
        if not order_id:
            return JsonResponse({'ret': 1, 'errmsg': '无效的订单id'})
        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)
        except OrderInfo.DoesNotExist as e:
            return JsonResponse({'ret': 2, 'errmsg': '订单错误'})
        # 业务处理 使用python SKD调用支付宝接口
        # 初始化
        alipay = AliPay(
            appid="2016092200569038",
            app_notify_url=None,  # 默认回调url
            app_private_key_path=os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem'),
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            alipay_public_key_path=os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem'),
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True,  # 默认False
        )
        # 调用支付接口
        total_pay = order.total_price+order.transit_price
        # 电脑网站支付，需要跳转到https://openapi.alipay.com/gateway.do? + order_string
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,  # 订单id
            total_amount=str(total_pay),  # 支付总金额
            subject="天天生鲜%s" % order_id,  # 名称
            return_url=None,
            notify_url=None  # 可选, 不填则使用默认notify url
        )
        # 放回应答
        pay_url = 'https://openapi.alipaydev.com/gateway.do?' + order_string
        return JsonResponse({'ret': 3, 'pay_url': pay_url})


# /order/check
# ajax post order_id
class OrderCheckView(View):
    """订单结果查询"""
    def post(self, request):
        """订单结果查询"""
        # 用户登录
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'ret': 0, 'errmsg': '用户未登录'})
        # 接受参数
        order_id = request.POST.get('order_id')
        # 校验参数
        if not order_id:
            return JsonResponse({'ret': 1, 'errmsg': '无效的订单id'})
        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)
        except OrderInfo.DoesNotExist as e:
            return JsonResponse({'ret': 2, 'errmsg': '订单错误'})
        # 业务处理 使用python SKD调用支付宝接口
        # 初始化
        alipay = AliPay(
            appid="2016092200569038",
            app_notify_url=None,  # 默认回调url
            app_private_key_path=os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem'),
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            alipay_public_key_path=os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem'),
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True,  # 默认False
        )
        # 调用支付宝交易查询接口
        while True:
            response = alipay.api_alipay_trade_query(order_id)
            """
                response = {
                  "alipay_trade_query_response": {
                    "trade_no": "2017032121001004070200176844",  # 支付宝交易号
                    "code": "10000",  # 支付状态
                    "invoice_amount": "20.00",
                    "open_id": "20880072506750308812798160715407",
                    "fund_bill_list": [
                      {
                        "amount": "20.00",
                        "fund_channel": "ALIPAYACCOUNT"
                      }
                    ],
                    "buyer_logon_id": "csq***@sandbox.com",
                    "send_pay_date": "2017-03-21 13:29:17",
                    "receipt_amount": "20.00",
                    "out_trade_no": "out_trade_no15",
                    "buyer_pay_amount": "20.00",
                    "buyer_user_id": "2088102169481075",
                    "msg": "Success",
                    "point_amount": "0.00",
                    "trade_status": "TRADE_SUCCESS",  # 支付结果
                    "total_amount": "20.00"
                  }"""
            code = response.get('code')
            if code == '10000' and response.get('trade_status') == 'TRADE_SUCCESS':
                # 支付成功
                # 获取支付宝交易号，更新订单状态
                trade_no = response.get('trade_no')
                order.trade_no = trade_no
                order.order_status = 4  # 待评价
                order.save()
                # 返回支付交易结果
                return JsonResponse({'ret': 3, 'message': '支付成功'})
            elif code == '40004' or (code == '10000' and response.get('trade_status') == 'WAIT_BUYER_PAY'):
                # 等待买家付款
                import time
                time.sleep(5)
                continue
            else:
                # 支付出错
                print(code)
                return JsonResponse({'ret': 4, 'errmsg': '支付出错'})


# /order.comment
class OrderCommentView(LoginRequiredMixin, View):
    def get(self, request, order_id):
        """订单评论页面"""
        # 验证登录用户
        user = request.user
        # 校验数据
        if not order_id:
            return redirect(reverse('user:order'))
        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist as e:
            return redirect(reverse('user:order'))
        # 根据订单的状态获取订单的标题
        order.status_name = OrderInfo.ORDER_STATUS[order.order_status]
        # todo: (order_id待定)获取订单商品详情信息
        order_skus = OrderGoods.objects.filter(order_id=order_id)
        for order_sku in order_skus:
            # 计算商品的小计
            amount = order_sku.count*order_sku.price
            # 动态增加小计
            order_sku.amount = amount
        # 动态给order增加属性order_skus, 保存订单商品信息
        order.order_skus = order_skus
        # 使用模板
        return render(request, 'order_comment.html', {'order': order})

    def post(self, request, order_id):
        """评论提交"""
        user = request.user
        # 校验数据
        if not order_id:
            return redirect(reverse('user:order'))
        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist as e:
            return redirect(reverse('user:order'))
        # 获取评论条数
        comment_count = request.POST.get('total_count')
        comment_count = int(comment_count)
        # 循环订单中的评论内容
        for i in range(1, comment_count+1):
            # 获取请论的商品的id
            sku_id = request.POST.get('sku_%d' % i)
            # 获取评论的商品的内容
            sku_comment = request.POST.get("content_%d" % i,'')
            try:
                order_goods = OrderGoods.objects.get(order_id=order_id, sku_id=sku_id)
            except OrderGoods.DoesNotExist as e:
                continue
            order_goods.comment = sku_comment
            order_goods.save()
        # 订单状态改变
        order.order_status = 5
        order.save()

        return redirect(reverse("user:order", kwargs={"page": 1}))
