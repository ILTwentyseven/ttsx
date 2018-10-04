from django.core.files.storage import Storage
from fdfs_client.client import Fdfs_client
from django.conf import settings


class FDFSStorage(Storage):
    def __init__(self, client_path=None, base_url=None):
        if client_path is None:
            client_path = settings.FDFS_CLIENT_PATH
        self.client_path = client_path
        if base_url is None:
            base_url = settings.FDFS_NGINX_BASE_URL
        self.base_url = base_url

    def _open(self, name, mode='rb'):
        pass

    def _save(self, name, content):
        # name:代表你要上传的文件的名字
        # content:包含你上传文件内容的file对象
        # 创建一个Fdfs_cilent对象
        client = Fdfs_client(self.client_path)
        # 上传文件至fast dfs系统中
        ret = client.upload_by_buffer(content.read())

        # dict {
        #             'Group name'      : group_name,
        #             'Remote file_id'  : remote_file_id,
        #             'Status'          : 'Upload successed.',
        #             'Local file name' : '',
        #             'Uploaded size'   : upload_size,
        #             'Storage IP'      : storage_ip
        #         }
        if ret.get('Status') != 'Upload successed.':
            # 上传失败
            raise Exception('文件上传失败')
        # 获取返回文件ID
        filename = ret.get('Remote file_id')
        return filename

    def exists(self, name):
        """Django判断文件名是否可用"""
        return False

    def url(self, name):
        """返回返回文件的url路径"""
        return self.base_url + name
