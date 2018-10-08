from django.shortcuts import render
from django.views import View
from django_redis import get_redis_connection
from django.http import JsonResponse
from goods.models import GoodsSKU
from utils.mixin import LoginRequiredMixin  # 判断用户是否登录
# Create your views here.

# 获取数据： 商品ID:sku_id, 商品数量:count
# cart/add
class CartAddView(View):
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



class CartInfoView(LoginRequiredMixin, View):
    """购物车模块"""
    def get(self, request):
        user = request.user
        # 接受数据
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        # 获取商品信息，得到的值是一个字典{‘商品id’： 数目}
        cart_dict = conn.hgetall(cart_key)

        skus = []
        # 购物车中商品的总数目和总价格
        total_count = 0
        total_price = 0
        # 遍历获取的商品的信息
        for sku_id, count in cart_dict.items():
            # 获取商品id
            sku = GoodsSKU.objects.get(id=sku_id)
            # 计算商品的小计
            amount = sku.price*int(count)
            # 动态给sku对象增加一个属性amount, 保存商品的小计
            sku.amount = amount
            # 动态给sku对象增加一个属性count, 保存购物车中对应商品的数量
            sku.count = int(count)
            # 添加
            skus.append(sku)
            # 计算商品合计和总件数
            total_count += int(count)
            total_price += amount
        # 组织模板上下文
        context = {'skus': skus,
                   'total_count': total_count,
                   'total_price': total_price}
        # 返回应答
        return render(request, 'cart.html', context)
