from celery import Celery
from django.conf import settings
from django.core.mail import send_mail
from django_redis import get_redis_connection
from django.template import loader
import time
# 在任务处理者一端加入,wsgi的启动django的初始化
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ttsx.settings')
django.setup()
# 在任务处理端如果上面没有初始化，它放在初始化之上会报错
from goods.models import GoodsType, GoodsSKU, IndexGoodsBanner,IndexPromotionBanner,IndexTypeGoodsBanner
# 创建一个celery的实例对象
app = Celery('celery_tasks.tasks', broker='redis://127.0.0.1:6379/8')


@app.task
def send_register_active_email(to_email, username, token):
    subject = '天天生鲜欢迎您'
    message = ''
    sender = settings.EMAIL_FROM
    receiver = [to_email]
    html_message = '<h>尊贵的%s,欢迎加入天天生鲜会员</h><br/><h>请点击下面的链接激活会员</h><br/><a href="http://127.0.0.1:8000/user/active/%s">http://127.0.0.1:8000/user/active/%s</a>' % (
    username, token, token)
    send_mail(subject, message, sender, receiver, html_message=html_message)
    # time.sleep(10)


@app.task
def generate_static_index_html():
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
    # 组织模板上下文
    context = {'types': types,
               'goods_banners': goods_banners,
               'promotion_banners': promotion_banners}
    # 使用模板
    temp = loader.get_template('static_index.html')
    # 渲染模板
    static_index_html = temp.render(context)
    # 生成首页对应的文件
    save_path = os.path.join(settings.BASE_DIR, 'static/index.html')
    with open(save_path, 'w') as f:
        f.write(static_index_html)
