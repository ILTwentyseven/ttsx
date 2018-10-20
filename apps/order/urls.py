from django.urls import path, re_path
from order.views import OrderPlaceView, OrderCommitView, OrderPayView, OrderCheckView, OrderCommentView

urlpatterns = [
    path('place/', OrderPlaceView.as_view(), name='place'),  # 提交订单页面显示
    re_path(r'^commit$', OrderCommitView.as_view(), name='commit'),  # 订单提交
    re_path(r'^pay$', OrderPayView.as_view(), name='pay'),  # 订单支付
    re_path(r'^check$', OrderCheckView.as_view(), name='check'),  # 订单结果查询
    re_path(r'^comment/(?P<order_id>.+)$', OrderCommentView.as_view(), name='comment')  # 订单评论
]