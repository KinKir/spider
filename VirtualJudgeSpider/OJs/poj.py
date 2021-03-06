import base64
import re

from bs4 import BeautifulSoup
from bs4.element import Tag

from VirtualJudgeSpider import config
from VirtualJudgeSpider.OJs.base import Base, BaseParser
from VirtualJudgeSpider.config import Problem, Result
from VirtualJudgeSpider.utils import HttpUtil, HtmlTag


class POJParser(BaseParser):
    def __init__(self, *args, **kwargs):
        self._static_prefix = 'http://poj.org/'

    def problem_parse(self, response, pid, url):
        problem = Problem()

        problem.remote_id = pid
        problem.remote_url = url
        problem.remote_oj = 'POJ'
        if response is None:
            problem.status = Problem.Status.STATUS_SUBMIT_FAILED
            return problem
        website_data = response.text
        status_code = response.status_code
        if status_code != 200:
            problem.status = Problem.Status.STATUS_SUBMIT_FAILED
            return problem
        if re.search('Can not find problem', website_data):
            problem.status = Problem.Status.STATUS_PROBLEM_NOT_EXIST
            return problem
        soup = BeautifulSoup(website_data, 'lxml')

        match_groups = re.search(r'ptt" lang="en-US">([\s\S]*?)</div>', website_data)
        if match_groups:
            problem.title = match_groups.group(1)
        match_groups = re.search(r'(\d*MS)', website_data)
        if match_groups:
            problem.time_limit = match_groups.group(1)
        match_groups = re.search(r'Memory Limit:</b> ([\s\S]*?)</td>', website_data)
        if match_groups:
            problem.memory_limit = match_groups.group(1)
        problem.special_judge = re.search(r'red;">Special Judge</td>', website_data) is not None
        problem.html = ''
        for tag in soup.find('div', attrs={'class': 'ptt'}).next_siblings:
            if type(tag) == Tag and set(tag.get('class')).intersection({'ptx', 'pst', 'sio'}):
                if set(tag['class']).intersection({'pst', }):
                    tag['style'] = HtmlTag.TagStyle.TITLE.value

                    tag['class'] += (HtmlTag.TagDesc.TITLE.value,)
                else:
                    tag['style'] = HtmlTag.TagStyle.CONTENT.value
                    tag['class'] += (HtmlTag.TagDesc.CONTENT.value,)
                problem.html += str(HtmlTag.update_tag(tag, self._static_prefix))
        problem.status = Problem.Status.STATUS_CRAWLING_SUCCESS
        return problem

    def result_parse(self, response):
        result = Result()
        if response is None or response.status_code != 200:
            result.status = Result.Status.STATUS_SUBMIT_FAILED
            return result
        soup = BeautifulSoup(response.text, 'lxml')
        line = soup.find('table', attrs={'class': 'a'}).find('tr', attrs={'align': 'center'}).find_all('td')
        if line is not None:
            result.origin_run_id = line[0].string
            result.verdict = line[3].string
            result.execute_time = line[5].string
            result.execute_memory = line[4].string
            result.status = Result.Status.STATUS_RESULT
        else:
            result.status = Result.Status.STATUS_SUBMIT_FAILED
        return result


class POJ(Base):
    def __init__(self, *args, **kwargs):
        self.code_type = 'utf-8'
        self._headers = config.custom_headers
        self._headers['Referer'] = 'http://poj.org/'
        self._headers['Content-Type'] = 'application/x-www-form-urlencoded'

        self._req = HttpUtil(custom_headers=self._headers, code_type=self.code_type, *args, **kwargs)

    @staticmethod
    def home_page_url():
        url = 'http://poj.org/'
        return url

    def get_cookies(self):
        return self._req.cookies.get_dict()

    def set_cookies(self, cookies):
        if type(cookies) == dict:
            self._req.cookies.update(cookies)

    # 登录页面
    def login_website(self, account, *args, **kwargs):
        if account and account.cookies:
            self._req.cookies.update(account.cookies)
        if self.check_login_status():
            return True
        login_page_url = 'http://poj.org/'
        login_link_url = 'http://poj.org/login'
        post_data = {'user_id1': account.username,
                     'password1': account.password,
                     'B1': 'login',
                     'url': '/'}
        self._req.get(url=login_page_url)
        self._req.post(url=login_link_url, data=post_data)
        return self.check_login_status()

    # 检查登录状态
    def check_login_status(self):
        url = 'http://poj.org/'
        res = self._req.get(url=url)
        if res and re.search(r'action=logout&', res.text):
            return True
        return False

    # 获取题目
    def get_problem(self, *args, **kwargs):
        pid = str(kwargs['pid'])
        url = 'http://poj.org/problem?id=' + pid
        res = self._req.get(url=url)
        return POJParser().problem_parse(res, pid, url)

    # 提交代码
    def submit_code(self, *args, **kwargs):
        if not self.login_website(*args, **kwargs):
            return False
        code = kwargs['code']
        language = kwargs['language']
        pid = kwargs['pid']
        url = 'http://poj.org/submit'
        if type(code) is str:
            code = bytes(code, encoding='utf-8')
        post_data = {'problem_id': pid,
                     'language': language,
                     'source': base64.b64encode(code),
                     'submit': 'Submit',
                     'encoded': '1'}
        res = self._req.post(url=url, data=post_data)
        if res and res.status_code == 200:
            return True
        return False

    # 获取当然运行结果
    def get_result(self, *args, **kwargs):
        account = kwargs.get('account')
        pid = kwargs.get('pid')
        url = 'http://poj.org/status?problem_id=' + pid + '&result=&language=&top=&user_id=' + account.username
        return self.get_result_by_url(url=url)

    # 根据源OJ的运行id获取结构
    def get_result_by_rid_and_pid(self, rid, pid):
        url = 'http://poj.org/status?problem_id=&result=&language=&top=' + str(int(rid) + 1)
        return self.get_result_by_url(url=url)

    # 根据源OJ的url获取结果
    def get_result_by_url(self, url):
        res = self._req.get(url=url)
        return POJParser().result_parse(res)

    # 获取源OJ支持的语言类型
    def find_language(self, *args, **kwargs):
        if self.login_website(*args, **kwargs) is False:
            return None
        url = 'http://poj.org/submit'
        language = {}
        res = self._req.get(url=url)
        if res:
            soup = BeautifulSoup(res.text, 'lxml')
            options = soup.find('select', attrs={'name': 'language'}).find_all('option')
            for option in options:
                language[option.get('value')] = option.string
        return language

    # 检查源OJ是否运行正常
    def check_status(self):
        url = "http://poj.org/"
        res = self._req.get(url)
        if res and re.search(r'color=blue>Welcome To PKU JudgeOnline</font>', res.text):
            return True
        return False

    @staticmethod
    def is_accepted(verdict):
        return verdict == 'Accepted'

    @staticmethod
    def is_running(verdict):
        return verdict in ['Queuing', 'Compiling', 'Waiting', 'Running & Judging']

    @staticmethod
    def is_compile_error(verdict):
        return verdict == 'Compile Error'
