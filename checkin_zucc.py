# -*- coding: UTF-8 -*-
import requests, os
import time
from lxml import etree
import random
import json
from halo import Halo
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.jobstores.base import JobLookupError
from pathlib import Path
import time, datetime
import argparse
import getpass

class CheckIn_ZUCC(object):
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.login_url = "http://ca.zucc.edu.cn/cas/login"
        self.base_url = "http://yqdj.zucc.edu.cn/feiyan_api/h5/html/index/index.html"
        self.referer_url = "http://yqdj.zucc.edu.cn/feiyan_api/h5/daka/daka.html"
        self.save_url = "http://yqdj.zucc.edu.cn/feiyan_api/examen/examenAnswerController/commitAnswer.do"
        self.query_url = "http://yqdj.zucc.edu.cn/feiyan_api/examen/examenAnswerController/queryBpaDate.do"
        self.examen_url = "http://yqdj.zucc.edu.cn/feiyan_api//examen/examenSchemeController/findExamenSchemeById.do"
        self.user_url = "http://yqdj.zucc.edu.cn/feiyan_api/auth/authController/getUserInfo.do"
        self.headers = {
            'Content-Type': 'application/json;charset=UTF-8'
        }
        self.session = requests.Session()
        self.info = {}

    def login(self):
        res=self.session.get(url=self.login_url)
        html = etree.HTML(res.text)
        code=html.xpath("/html/body/div/form/div[3]/div/div/div[5]/input[2]/@value")[0]

        data={
        'authType': '0',
        'username': self.username, 
        'password': self.password,
        'lt': '',
        'execution': code,
        '_eventId': 'submit',
        'submit': '',
        'randomStr': ''
        }

        res=self.session.post(url=self.login_url,data=data)
        if '统一身份认证' in res.content.decode():
            raise LoginError('登录失败，请核实账号密码重新登录')
        res = self.session.get(self.base_url)

    def get_info(self):
        #获取历史问卷信息
        res=self.session.post(url=self.query_url,
            data={'cdata' : self.get_date(-1)})
        res = json.loads(res.content)
        if res['code'] != 1000:
            raise RegexMatchError("未发现缓存信息，请先至少手动成功打卡一次再运行脚本")
        self.info['answer'] = json.loads(res['data']['answer'])

        #获取用户信息
        res=self.session.post(self.user_url)
        res = json.loads(res.content)
        self.info['number']=res['data']['account']
        self.info['name']=res['data']['realName']

        
        
    def get_date(self, day_offset : int = 0):
        date = datetime.date.today().__add__(datetime.timedelta(day_offset))
        return "%4d-%02d-%02d"%(date.year, date.month, date.day)

    def post(self):
        answer = self.info['answer']
                #获取问卷信息
        res=self.session.post(url=self.examen_url,
            data={'esId' : 2})
        res = json.loads(res.content)
        self.info['questions'] = json.loads(res['data']['examen']['scheme'])['questions']
        return_value = None
        for question in self.info['questions']:
            if not question['title'] in answer:
                return_value = {
                'e':-1,
                'm':"发现未缓存信息 "+question['title']+" ，请重新手动成功打卡一次再运行脚本"
                }
                break

        answer['填报日期'] = self.get_date()
        data = {
            "examenSchemeId":
            2,
            "examenTitle":
            "师生报平安",
            "answer":
            json.dumps(answer, ensure_ascii= False)
        }
        headers = self.headers
        _json = json.dumps(data, ensure_ascii= False).encode('utf-8')
        res=self.session.post(url=self.save_url,
        data=_json,
        headers=headers)
        res = json.loads(res.content)
        if('请勿重复提交问卷' == res['message']):
            return {
                'e':res['code'],
                'm':'今天已打卡成功'
            }
        if(1000 == res['code']):
            return {'e':0}
        if return_value:
            return return_value
        return {
                'e':res['code'],
                'm':res['message']
            }

class LoginError(Exception):
    """Login Exception"""
    pass

class RegexMatchError(Exception):
    """Regex Matching Exception"""
    pass

scheduler = BlockingScheduler()
hour = 0
minute = 5

def main(username, password):
    """Hit card process

    Arguments:
        username: (str) 浙大统一认证平台用户名（一般为学号）
        password: (str) 浙大统一认证平台密码
    """
    try:
        scheduler.remove_job('checkin_zucc_ontime')
    except JobLookupError as e:
        pass

    print("\n[Time] %s" %datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("🚌 打卡任务启动")
    spinner = Halo(text='Loading', spinner='dots')
    spinner.start('正在新建打卡实例...')
    ci = CheckIn_ZUCC(username, password)
    spinner.succeed('已新建打卡实例')

    spinner.start(text='登录到浙大城院统一身份认证平台...')
    try:
        ci.login()
        spinner.succeed('已登录到浙大城院统一身份认证平台')
    except Exception as err:
        spinner.fail(str(err))
        return

    spinner.start(text='正在获取个人信息...')
    try:
        ci.get_info()
        spinner.succeed('%s %s同学, 你好~' %(ci.info['number'], ci.info['name']))
    except Exception as err:
        spinner.fail('获取信息失败，请手动打卡，更多信息: ' + str(err))
        return

    spinner.start(text='正在为您打卡打卡打卡')
    try:
        res = ci.post()
        if str(res['e']) == '0':
            spinner.stop_and_persist(symbol='🦄 '.encode('utf-8'), text='已为您打卡成功！')
        else:
            spinner.stop_and_persist(symbol='🦄 '.encode('utf-8'), text=res['m'])

        # Random time
        random_time = random.randint(0, 60) + hour * 60 + minute
        random_hour = random_time // 60
        random_minute = random_time % 60
        weekday = (datetime.datetime.now().weekday() + 1) % 7

        # Schedule task
        scheduler.add_job(main, 'cron', id='checkin_zucc_ontime', args=[username, password], day_of_week=weekday, hour=random_hour, minute=random_minute)
        print('⏰ 已启动定时程序，明天 %02d:%02d 为您打卡' %(int(random_hour), int(random_minute)))
        print('Press Ctrl+{0} to exit'.format('Break' if os.name == 'nt' else 'C'))
    except:
        spinner.fail('数据提交失败')
        return 


# def test():
#     try:
#         scheduler.remove_job('checkin_ontime')
#     except JobLookupError as e:
#         pass
#     print("\n[Time] %s" %datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
#     print("Run once")

#     # Schedule task
#     random_time = random.randint(-10, 10)
#     print(random_time)
#     hour = int(datetime.datetime.now().strftime('%H'))
#     minute = int(datetime.datetime.now().strftime('%M'))
#     if minute + 1 >= 60:
#         hour += 1
#         minute = 0
#     if hour >= 24:
#         hour = 0
#     scheduler.add_job(test, 'cron', id='checkin_ontime', hour=hour, minute=minute + 1, second=30 + random_time)


def parse_args():
    parser = argparse.ArgumentParser("Auto CheckIn")
    parser.add_argument("-c", "--config", action="store_true", help="Use config file")
    args = parser.parse_args()
    return args


if __name__=="__main__":
    args = parse_args()
    cfg_file = Path(__file__).parent / "config.json"

    if  args.config and cfg_file.exists():
        configs = json.loads(cfg_file.read_bytes())
        username = configs["username"]
        password = configs["password"]
        hour = int(configs["schedule"]["hour"])
        minute = int(configs["schedule"]["minute"])
    else:
        username = input("👤 浙大城院统一认证用户名: ")
        password = getpass.getpass('🔑 浙大城院统一认证密码: ')
        print("⏲  请输入锚点时间(默认为 00:05, 向上浮动1小时, 如 00:05 将对应 00:05-01:05 打卡):")
        hour = input("\thour: ") or hour
        hour = int(hour)
        minute = input("\tminute: ") or minute
        minute = int(minute)

    main(username, password)

    # test()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
