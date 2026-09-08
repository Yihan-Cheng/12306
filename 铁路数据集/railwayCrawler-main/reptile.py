from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
import time, csv, os

chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--window-size=1920,1080')

mainpage = 'http://cnrail.geogv.org/zhcn/about'

stations = ['上海', '上海南', '上海虹桥', '上饶', '中卫', '中卫南', '临汾', '临汾西', '丹东', '乌兰浩特', '乌鲁木齐', '乐山', '九江', '二连', '伊图里河', '佳木斯', '兰州', '兰州西', '内江', '内江北', '凭祥', '加格达奇', '包头', '包头东', '北京', '北京北', '北京南', '北京西', '北安', '北海', '十堰', '十堰东', '华山', '华山北', '南京', '南京南', '南宁', '南宁东', '南宁西', '南昌', '南昌西', '南通', '南通西', '厦门', '厦门北', '双辽', '合肥', '合肥南', '吉林', '吐鲁番', '启东', '呼和浩特', '呼和浩特东', '咸宁', '咸宁北', '咸宁南', '哈尔滨', '哈尔滨东', '哈尔滨西', '喀什', '嘉峪关', '嘉峪关南', '四平', '四平东', '图们北', '大同', '大同南', '大庆', '大庆东', '大庆西', '大明湖', '大虎山', '大连', '大连北', '天水', '天水南', '天津', '天津北', '天津西', '太原', '太原南', '奎屯', '孝感', '孝感东', '宁波', '安庆', '安顺', '安顺西', '宋城路', '宜宾', '宜宾西', '宝鸡', '宝鸡南', '宣城', '富裕', '山海关', '常州', '常州北', '平顶山', '平顶山西', '广元', '广州', '广州东', '广州南', '库尔勒', '开封', '开封北', '徐州', '徐州东', '德州', '德州东', '怀化', '怀化南', '成都', '成都东', '成都南', '成都西', '承德', '承德东', '承德南', '抚顺北', '拉萨', '敦化', '新乡', '新乡东', '新沂', '日喀则', '日照', '日照西', '昆明', '昆明南', '昭通', '曲阜', '曲阜东', '杭州', '杭州东', '杭州南', '柳州', '株洲', '格尔木', '桂林', '桂林北', '桂林西', '桑根达来', '梅河口', '武昌', '武汉', '汉口', '江油', '沈阳', '沈阳北', '沈阳南', '洛阳', '洛阳龙门', '济南', '济南东', '济南西', '海安', '海拉尔', '淮南', '淮南东', '淮南南', '深圳', '深圳北', '温州', '温州南', '湘潭', '满归', '满洲里', '漯河', '漯河西', '烟台', '烟台南', '焦作', '牙克石', '牡丹江', '玉溪', '珲春', '白城', '百色', '盐城', '石家庄', '石家庄东', '石家庄北', '福利屯', '福州', '福州南', '福田', '绥德', '绥芬河', '胶州', '胶州北', '芜湖', '苏州', '苏州北', '荣成', '蚌埠', '蚌埠南', '衡阳', '衡阳东', '衢州', '襄州', '襄阳', '襄阳东', '西宁', '贵阳', '贵阳东', '贵阳北', '赣州', '赣州西', '达州', '连云港', '连云港东', '通辽', '邯郸', '邯郸东', '郑州', '郑州东', '重庆', '重庆北', '重庆西', '金华', '金华南', '铜陵', '铜陵北', '银川', '锡林浩特', '锦州', '锦州南', '长春', '长春西', '长沙', '长沙南', '长治', '长治北', '阜阳', '阜阳西', '防城港北', '阿勒泰', '阿尔山', '阿尔山北', '雅安', '集宁南', '霍尔果斯', '霍林郭勒', '青城山', '青岛', '青岛北', '鹤岗', '鹰潭', '鹰潭北', '黄山', '黄山北', '黄石', '黄石北', '黑河', '齐齐哈尔', '乌兰察布', '攀枝花', '攀枝花南', '商丘', '商丘南', '商丘东', '开阳', '宜昌东', '利川', '张家界', '张家界西', '常德', '黔江', '张家口', '潍坊', '潍坊北', '吐鲁番北', '婺源', '原平', '原平西', '隆化', '天津南', '鄂尔多斯', '西安', '秦皇岛', '西安北', '遂宁', '万州', '兰州东', '深圳西', '珠海', '湘潭北', '绥化', '云梦', '漠河', '抚远', '和田', '万州北', '怀柔北', '鄂州', '青岛西', '株洲西', '嘉兴南', '聊城', '衡水', '那曲', '汉中', '安康', '丽水', '兖州', '济宁', '菏泽', '延安', '榆林', '吉安', '吉安西', '西安南', '信阳', '信阳东', '南阳', '南阳东', '沙坪坝', '深圳东', '六盘水'] # '湛江', '湛江西', '茂名', '茂名西', '阿拉山口', '古莲'

def seekurl(station):
    driver = webdriver.Chrome('chromedriver',chrome_options=chrome_options)
    print('request mainpage..', station)
    driver.get(mainpage)
    print('done..', station)
    original_url = driver.current_url

    while True:
        try:
            searchbox = driver.find_element('xpath', '/html/body/div/nav/div/div[1]/div/input')
        except: pass
        else: break

    print('searchbox attained..')

    searchbox.send_keys(station)

    driver.implicitly_wait(10)
    for i in range(1, 10):
        '''
        print('option {}'.format(i))
        while True:
            try:
                name = driver.find_element('xpath', '/html/body/div/nav/div/div[1]/div/ul/li[{}]/a/div'.format(i)).text
            except: driver.implicitly_wait(1) # stuck here, unknown reasons
            else: break
        '''

        try:
            name = driver.find_element('xpath', '/html/body/div/nav/div/div[1]/div/ul/li[{}]/a/div'.format(i)).text
        except: return None
        else: pass

        if station == name:
            option = driver.find_element('xpath', '/html/body/div/nav/div/div[1]/div/ul/li[{}]'.format(i))
            option.click()
            #driver.implicitly_wait(10)
            url = driver.current_url
            while url == original_url:
                url = driver.current_url
                print('waiting on url')
            driver.quit()
            return url

def grasp_csv(url):
    driver = webdriver.Chrome('chromedriver',chrome_options=chrome_options)
    print('grasp csv page..', url)
    driver.get(url)
    #driver.implicitly_wait(10)
    print('done..', url)

    while True:
        try:
            button = driver.find_element('xpath', '/html/body/div/div[4]/div/div[2]/div[2]/div[2]/button[1]')
            button.send_keys(Keys.ENTER) # button for all routes
        except: pass
        else: break
    #driver.implicitly_wait(10)
    print('button clicked..', url)
    
    length = 0
    while True:
        try:
            table = driver.find_element('xpath', '/html/body/div[1]/div/div/station-route-view/div[2]/table/tbody')
            routes = table.find_elements_by_tag_name('tr')
        except: pass
        else:
            if (len(routes) > 0 and length == len(routes)): break
            length = len(routes)
            driver.implicitly_wait(1)
    
    '''
    table = driver.find_element('xpath', '/html/body/div[1]/div/div/station-route-view/div[2]/table/tbody')
    routes = table.find_elements_by_tag_name('tr')
    '''
    
    scheduler = []
    for route in routes:
        service = route.find_element_by_xpath('td[1]/span').text
        passby = route.find_element_by_xpath('td[2]/span[1]').text
        train = route.find_element_by_xpath('td[2]/a').text
        original = route.find_element_by_xpath('td[3]/div').text
        terminus = route.find_element_by_xpath('td[4]/div').text
        arrival = route.find_element_by_xpath('td[5]').text
        departure = route.find_element_by_xpath('td[6]').text

        record = [service, passby, train, original, terminus, arrival, departure]
        scheduler.append(record)
    
    driver.quit()
    return scheduler
    #print(routes.get_attribute('innerHTML'))
    #print(driver.page_source)
    
for station in stations:
    filename = './schedulers/{}.csv'.format(station)
    if os.path.isfile(filename): continue

    print(time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(time.time())))
    url = seekurl(station)
    if (url == None):
        print('Error was raised, {} was skipped'.format(station))
        continue
    print(station, url)
    schedulars = grasp_csv(url)
    with open(filename, 'a', encoding = 'gbk') as f:
        writer = csv.writer(f)
        writer.writerows(schedulars)