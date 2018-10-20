from django.shortcuts import render, redirect
from django.urls import reverse
from goods.models import GoodsType, GoodsSKU, IndexGoodsBanner, IndexPromotionBanner, IndexTypeGoodsBanner
from order.models import OrderGoods
from django_redis import get_redis_connection
from django.views.generic import View
from django.core.cache import cache  # 设置缓存
from django.core.paginator import Paginator  # 对数据进行分页
# Create your views here.


# goods/index
class IndexView(View):
    """商品首页"""
    def get(self, request):
        # 接受缓存
        context = cache.get('index_page_data')
        # 判断是否有缓存。没有就设置。有就跳过执行下一步
        if context is None:
            print('设置缓存')
            # 获取商品的种类信息
            types = GoodsType.objects.all()
            # 获取首页轮播商品信息
            goods_banners = IndexGoodsBanner.objects.all().order_by('index')
            # 获取首页促销活动信息
            promotion_banners = IndexPromotionBanner.objects.all().order_by('index')
            # 获取首页分类商品展示信息
            for type in types:  # GoodsType
                # 获取type种类首页分类商品的图片展示信息
                image_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1).order_by('index')
                # 获取type种类首页分类商品的文字展示信息
                title_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0).order_by('index')
                # 动态给type增加属性，分别保存首页分类商品的图片展示信息和文字展示信息
                type.image_banners = image_banners
                type.title_banners = title_banners
            context = {'types': types,
                       'goods_banners': goods_banners,
                       'promotion_banners': promotion_banners}
            # 设置缓存
            cache.set('index_page_data', context, 3600)
        # 获取用户购物车中商品的数目
        user = request.user
        cart_count = 0
        if user.is_authenticated:
            # 用户已登录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)

        # 组织模板上下文
        context.update(cart_count=cart_count)
        # 使用模板
        return render(request, 'index.html', context)


class DetailView(View):
    """商品详情页"""
    def get(self, request, goods_id):
        # 判断商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=goods_id)
        except GoodsSKU.DoesNotExist:
            # 商品不存在
            return redirect(reverse('goods: index'))
        # 获取商品分类
        types = GoodsType.objects.all()
        # 获取商品评论信息
        order_comment = OrderGoods.objects.filter(sku=sku).exclude(comment='')
        # 获取新品推荐
        new_goods = GoodsSKU.objects.filter(type=sku.type).order_by('-create_time')[:2]
        # 获取相同SPU的规格的产品
        same_spu_goods = GoodsSKU.objects.filter(goods=sku.goods).exclude(id=goods_id)
        # 获取用户购物车中商品的数目
        user = request.user
        cart_count = 0
        if user.is_authenticated:
            # 用户已登录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)
            # 添加历史浏览记录
            conn = get_redis_connection('default')
            history_key = 'history_%d' % user.id
            # 移除列表中的goods_id
            conn.lrem(history_key, 0, goods_id)
            # 将goods_id插入之列表左侧
            conn.lpush(history_key, goods_id)
            # 只保留五条浏览记录
            conn.ltrim(history_key, 0, 4)

        # 组织模板上下文
        context = {'types': types,
                   'order_comment': order_comment,
                   'new_goods': new_goods,
                   'same_spu_goods': same_spu_goods,
                   'cart_count': cart_count,
                   'sku': sku}

        return render(request, 'detail.html', context)


# list/列表种类/页码
# list/种类id/页码?sort=page
class ListView(View):
    def get(self, request, type_id, page):
        # 判断种类是否存在
        try:
            type = GoodsType.objects.get(id=type_id)
        except GoodsType.DoesNotExist:
            return redirect(reverse('goods:index'))
        sort = request.GET.get('sort')
        # 获取商品的分类信息
        types = GoodsType.objects.all()
        # 根据不同的排序方式进行列表显示
        # 按照价格排序
        if sort == 'price':
            skus = GoodsSKU.objects.filter(type=type).order_by('price')
        # 按照销量排序
        elif sort == 'hot':
            skus = GoodsSKU.objects.filter(type=type).order_by('-sales')
        else:
            sort = 'default'
            skus = GoodsSKU.objects.filter(type=type).order_by('-id')

        # 对数据进行分页
        paginator = Paginator(skus, 2)
        # 获取第page页的内容
        try:
            page = int(page)
        except Exception as e:
            page = 1
        if page > paginator.num_pages:
            page = 1
        # 获取当前page页的内容
        skus_page = paginator.page(page)
        # 页码控制，最多显示五页
        # 总页数小于五页。显示全部页码
        # 如果当前页式前三页显示1-5页
        # 如果当前页式后三页显示最后五页
        # 其他情况，显示当前页的前两页，当前页和后两页
        num_pages = paginator.num_pages
        if num_pages < 5:
            pages = range(1, num_pages+1)
        elif num_pages <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages-4, num_pages+1)
        else:
            pages = range(page-2, page+3)
        # 获取新品推荐
        new_goods = GoodsSKU.objects.filter(type=type).order_by('-create_time')[:2]
        # 获取用户购物车中商品的数目
        user = request.user
        cart_count = 0
        if user.is_authenticated:
            # 用户已登录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)
        # 组织模板上下文
        context = {'type': type, 'types': types,
                   'skus': skus,
                   'skus_page': skus_page,
                   'sort': sort,
                   'new_goods': new_goods,
                   'cart_count': cart_count,
                   'pages': pages}
        return render(request, 'list.html', context)
