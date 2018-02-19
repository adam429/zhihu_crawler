# Zhihu Crawler 
#
#    Adam429 (adam429.lee@gmail.com)
#
# https://github.com/adam429/zhihu_crawler

from selenium.common.exceptions import TimeoutException
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from bs4 import BeautifulSoup
from multiprocessing import Process
from functools import reduce
import os
import re
import time
import json
import random
import logging
import datetime

### Configuration Start ###
config = {
            "topics":["制服"], 
            "search":["制服"],
            "output":"./output/",
            "answer_limit":"500",
            "jobs":"2",
         } 
### Configuration End ###

# Init Logger
logFormatStr = '[%(asctime)s] p%(process)s {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s'
formatter = logging.Formatter(logFormatStr,'%m-%d %H:%M:%S')
fileHandler = logging.FileHandler("zhihu_crawler.log")
fileHandler.setLevel(logging.INFO)
fileHandler.setFormatter(formatter)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(fileHandler)

# Log Function
def log(msg):
    try:
        logger.info(msg)
        print(msg)
    except OSError as e:
        pass

# Execute javascript to scroll down the button of the page.
# Trigger page loading
# Stop when page source code not change. Use for search page
def scroll_down_all_equal(driver):
    now = driver.page_source
    #
    while True:
        while True:
            last = now
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.1)
            now = driver.page_source
            # If there is no new item is loaded. Which means HTML equals previous state HTML
            # Then we know we reach page bottom
            if now==last:  
                break
        # Let's wait 5 more seconds to check if the HTML won't change.
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(5)
        now = driver.page_source    
        if now==last:
            break

# Execute javascript to scroll down the button of the page.
# Trigger page loading
# Stop when page match xpath. Use for question page
def scroll_down_all_match(driver,url):
    now = driver.page_source
    cnt = 1
    #
    while True:   
        # Find all answer count in question page
        soup = BeautifulSoup(driver.page_source,'lxml')
        try:
            a_count = _number(soup.find('',{'class':'List-headerText'}).text)
        except AttributeError:
            a_count = "N/A"
        count = len(soup.findAll('div',{'class':'List-item'}))
        log ("[{3}] Current Answer {0} / Total Answer {1} {2}".format(count,a_count,datetime.datetime.fromtimestamp(time.time()).strftime('[%Y-%m-%d %H:%M:%S]'),os.getpid()))
        # Save CSV file every 100 answers
        if int(count/100)>cnt:
            log ("Saving #{0} at {1}".format(cnt,count))
            cnt = int(count/100)
            save_answer(driver,_number(url))
        # If reach answer_list, then stop Scroll down
        if count>_to_number(config["answer_limit"]):
            save_answer(driver,_number(url))
            break
        # Scroll down
        last = now
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        driver.find_element_by_xpath("//body").send_keys(Keys.PAGE_DOWN)
        driver.find_element_by_xpath("//body").send_keys(Keys.PAGE_DOWN)
        time.sleep(0.05)
        now = driver.page_source
        # If reach page button, here is a button "Post New Answer" or a button "Post First Answer"
        # When we saw this button, we know we reach page bottom
        try:
            driver.find_element_by_xpath("//button[@class='Button QuestionAnswers-answerButton Button--blue Button--spread']")
            return
        except NoSuchElementException:
            pass
        #    
        try:
            driver.find_element_by_xpath("//button[@class='Button QuestionAnswers-answerLink Button--plain Button--blue']")
            return
        except NoSuchElementException:
            pass
        #    
        try:
            driver.find_element_by_xpath("//div[@class='CollapsedAnswers-bar']")
            return
        except NoSuchElementException:
            pass

# Get number part of a string
def _number(text):
    return re.sub('[^0-9]','',text)

# Convert to number
def _to_number(text):
    try:
        return int(_number(text))
    except ValueError:
        return 0
    except TypeError:
        return 0

# Format the string to fit the output CSV. 
def _csv(text):
    text = str(text)
    text = re.sub("\n","|",text)
    text = re.sub(",",".",text)
    return text

# Save fetched answer list to a file
def save_answer(driver,question_id):
    data = parse_answer(driver)
    #
    global config
    f=open(config['output']+question_id+".csv","w")
    f.write("\uFEFF")
    f.write("title,{0} \n".format(_csv(data["question"]["title"])))
    f.write("body,{0} \n".format(_csv(data["question"]["body"])))
    f.write("answer_count,{0} \n".format(_csv(data["question"]["answer_count"])))
    f.write("followed,{0} \n".format(_csv(data["question"]["followed"])))
    f.write("viewed,{0} \n".format(_csv(data["question"]["viewed"])))
    f.write("comments,{0} \n".format(_csv(data["question"]["comments"])))
    f.write("\n")
    f.write("user_name,user_url,user_desc,likes,edit_at,create_at,comments,body\n")
    for i in data["answer"]:
        f.write("{0},{1},{2},{3},{4},{5},{6},{7}\n".format(_csv(i["user_name"]),_csv(i["user_url"]),_csv(i["user_desc"]),_csv(i["likes"]),_csv(i["edit_at"]),_csv(i["create_at"]),_csv(i["comments"]),_csv(i["body"])))
    f.close()
    # Check the answer count in page, and actual fetched answer list number
    # If the number is the same, it is great.
    # If the number is not the same, there maybe some answer we did not fetched.
    if _to_number(data["question"]["answer_count"])-5>len(data["answer"]):
        log ("[{2}]Incomplete Answers {0},{1}".format(_to_number(data["question"]["answer_count"]),len(data["answer"]),os.getpid()))

# Save all questions to a index csv file
def save_index(question_list):
    global config
    log("[{0}]Indexing...".format(os.getpid()))
    f=open(config['output']+"index.csv","w")
    f.write("\uFEFF")
    f.write("question_id,question_url,answer_count,question\n")
    for i in question_list:
        try:
            count,actual_count=load_counts(config['output']+_number(i[0])+".csv")            
            f.write("{0},{1},{2},{3}\n".format(_number(i[0]),i[0],actual_count,_csv(i[1])))
        except FileNotFoundError:
            log("[{1}]{0} File Error".format(_number(i[0]),os.getpid()))
    f.close()

# Fetch all answers for a single question
def get_answer(driver,url):
    # Open URL
    driver.get(url)
    #
    # Click show all button
    input=driver.find_element_by_xpath('//div[@class="QuestionHeader-detail"]')
    input.click()
    #
    # Load all answers by scroll down
    scroll_down_all_match(driver,url)

# Parse answers from webdriver html
def parse_answer(driver):
    # Parse HTML Page
    soup = BeautifulSoup(driver.page_source,'lxml')
    #
    # Parse Question
    try:
        a_count = _number(soup.find('',{'class':'List-headerText'}).text)
    except AttributeError:
        a_count = "N/A"
    data = {}
    data["question"] = {
        "title": soup.find('',{'class':'QuestionHeader-title'}).text,
        "body": soup.find('',{'class':'QuestionHeader-detail'}).text,
        "answer_count": a_count,
        "followed": soup.findAll('',{'class':'NumberBoard-itemValue'})[0].attrs.get('title'),
        "viewed": soup.findAll('',{'class':'NumberBoard-itemValue'})[1].attrs.get('title'),
        "comments": _number(soup.find('div',{'class':'QuestionHeader-Comment'}).button.text),
    }
    data["answer"] = []
    #
    # Parse Each Answer
    for i in soup.findAll('div',{'class':'List-item'}):
        try:
            user_name = i.findAll('a',{'class':'UserLink-link'})[1].text
            user_url = i.findAll('a',{'class':'UserLink-link'})[1].attrs.get("href")
        except IndexError:
            user_name = "知乎用户"
            user_url = "N/A"
        #
        try:
            user_desc = i.find('div',{'class':'AuthorInfo-badgeText'}).text
        except AttributeError:
            user_desc = "N/A"
        #
        try:
            likes = _number(i.find('span',{'class':'Voters'}).text)
        except AttributeError:
            likes = "N/A"
        #
        try:
            edit_at = i.find('div',{'class':'ContentItem-time'}).span.text
            created_at = i.find('div',{'class':'ContentItem-time'}).span.attrs.get("data-tooltip")
        except AttributeError:
            edit_at = "N/A"
            created_at = "N/A"
        #
        try:
            comments = _number(i.find('button',{'class':'Button ContentItem-action Button--plain Button--withIcon Button--withLabel'}).text)
        except AttributeError:
            comments = "N/A"
        #
        try:
            body = i.find('div',{'class':'RichContent'}).text
        except AttributeError:
            body = "N/A"
        #
        answer = {
            "user_name": user_name,
            "user_url": user_url,
            "user_desc": user_desc,
            "likes": likes,
            "edit_at": edit_at,
            "create_at": created_at,
            "comments" : comments, 
            "body" : body
        }
        data["answer"].append(answer)
    #
    return data

# Load Question List from Topic & Keyword Search
# First time load from webdriver HTML parse, and save to JSON file
# Start from second time load from JSON file
def load_question_list(driver):
    try:
        question_list = json.load(open(config["output"]+"question_list.json"))
    except FileNotFoundError:
        all_item = []
        #
        # Load Topic
        for topic in config["topics"]:
            driver.get("https://www.zhihu.com/search?q={0}&type=content".format(topic))
            soup = BeautifulSoup(driver.page_source,'lxml')
            item = soup.find('a',{'class':'TopicLink'})
            topic_id = _number(item.attrs.get("href"))
            #
            # Part1 - Top Answers
            driver.get("https://www.zhihu.com/topic/{0}/top-answers".format(topic_id))
            scroll_down_all_equal(driver)
            soup = BeautifulSoup(driver.page_source,'lxml')
            items = soup.findAll('a',{'data-za-detail-view-element_name':'Title'})
            all_item = all_item + items
            #
            # Part2 - Hot Answers
            driver.get("https://www.zhihu.com/topic/{0}/hot".format(topic_id))
            scroll_down_all_equal(driver)
            soup = BeautifulSoup(driver.page_source,'lxml')
            items = soup.findAll('a',{'data-za-detail-view-element_name':'Title'})
            all_item = all_item + items
        #
        question_list = list(map(lambda x:[x.attrs.get("href"),x.text],all_item))
        question_list = list(filter(lambda x:not re.search('zhuanlan',x[0]),question_list))
        question_list = list(map(lambda x:["https://www.zhihu.com"+re.sub('/answer/.+','',x[0]),x[1]],question_list))
        #
        all_item = []
        # Load Search Keywords
        for keyword in config["search"]:
            driver.get("https://www.zhihu.com/search?type=content&q={0}".format(keyword))
            scroll_down_all_equal(driver)
            soup = BeautifulSoup(driver.page_source,'lxml')
            items = soup.findAll('div',{'itemprop':'zhihu:question'})
            all_item = all_item + items
        #
        question_list2 = list(map(lambda x:[x.a.attrs.get("href"),x.text],all_item))
        question_list2 = list(map(lambda x:["https://www.zhihu.com"+re.sub('/answer/.+','',x[0]),x[1]],question_list2))
        # Merge together
        question_list = question_list+question_list2
        # Save questions list
        #
        # Reduce duplications 
        func = lambda x,y:x if y in x else x + [y]
        question_list=reduce(func, [[], ] + question_list)
        #
        # Save to a json. 
        file = open(config['output']+"question_list.json","w")
        savedata = json.dumps(question_list)
        file.write(savedata)
        file.close()        
    #
    log("[{0}]Question Count:{1}".format(os.getpid(),str(len(question_list))))    
    return question_list

# Init Webdriver
def init_driver():
    options = webdriver.chrome.options.Options()
    options.add_argument('headless')
    options.add_argument('no-sandbox')  
    options.add_argument('window-size=1920,1080')
    options.add_argument('disable-gpu')
    prefs = {"profile.managed_default_content_settings.images":2}
    options.add_experimental_option("prefs",prefs)
    driver = webdriver.Chrome(chrome_options=options)
    return driver

# Run Fetch
def run_fetch():
    # Init WebDriver
    driver = init_driver()
    question_list = load_question_list(driver)
    # Random question_list
    random.shuffle(question_list)
    for i in question_list:
        log ("[{2}]Processing {0},{1}".format(_number(i[0]),i[0],os.getpid()))
        try:
            # If file existing, skip
            f=open(config['output']+_number(i[0])+".csv","r")
            f.close()
            log ("[{0}]..File Exist. Skip Fetch".format(os.getpid()))
        except FileNotFoundError:
            try:
                # If other worker are working, skip
                f=open(config['output']+"_"+_number(i[0])+".csv","r")
                f.close()
                log ("[{0}]..Other Worker are Sorking. Skip Fetch".format(os.getpid()))
            except FileNotFoundError:
                f=open(config['output']+"_"+_number(i[0])+".csv","w")
                f.write("placeholder")
                f.close()
                get_answer(driver,i[0])
                save_answer(driver,_number(i[0]))
                os.remove(config['output']+"_"+_number(i[0])+".csv")
                log ("[{0}]..Done".format(os.getpid()))            

# Runner Function
def run():
    global config
    # Create Output Directory if not exist
    if not os.path.exists(config["output"]):
        os.makedirs(config["output"])
    # Init WebDriver
    driver = init_driver()
    #
    # Load Question List
    question_list = load_question_list(driver)
    driver.close()
    #
    # Start fetch one by one
    #
    jobs = []
    for i in range(0,_to_number(config["jobs"])):
        log ("Start Process #{0}".format(str(i)))
        p = Process(target=run_fetch, args=())
        p.start()
        jobs.append(p)
    for i in jobs:
        i.join()
    #
    # Save Index
    save_index(question_list)

# Load CSV file to get count, and actual count 
def load_counts(filename):
    file=open(filename,"r")
    _=file.readline() 
    _=file.readline() 
    count=_to_number(file.readline().split(',')[1]) # answer_count
    _=file.readline() # followed
    _=file.readline() # viewed
    _=file.readline() # comments
    _=file.readline() # \n
    _=file.readline() # user_name,user_url,user_desc,likes,edit_at,create_at,comments,body\n
    actual_count=0
    while file.readline():
        actual_count=actual_count+1
    file.close()   
    #
    return count,actual_count

# Helper function 
def check_incomplete():
    global config
    #
    question_list = json.load(open(config["output"]+"question_list.json"))
    incomplete_list=[]
    #
    for i in question_list:
        try:
            count,actual_count=load_counts(config['output']+_number(i[0])+".csv")
            if actual_count<count-5:
                log ("[{2}]Incomplete {0},{1}".format(_number(i[0]),i[0],os.getpid()))
                incomplete_list = incomplete_list+[config['output']+_number(i[0])+".csv"]
        except FileNotFoundError:
            log("File Missing {0}".format(i[0]))
            pass
    #
    for i in incomplete_list:
        os.remove(i)

# Helper function 
def download_img():
    global config
    #
    if not os.path.exists(config["output"]+"img/"):
        os.makedirs(config["output"]+"img/")
    #
    question_list = json.load(open(config["output"]+"question_list.json"))
    img_list =[]
    #
    for i in question_list:
        try:
            file=open(config['output']+_number(i[0])+".csv","r")
            content = file.read()
            file.close()
            img_list = img_list + re.findall('src="([^"]*)',content)
        except FileNotFoundError:
            log("File Missing {0}".format(i[0]))
            pass
    #
    for i in img_list:
        os.system("curl {0} > {1}".format(i,config["output"]+"img/"+re.sub('^([^/]*/+)*','',i)))            




# Main program
if __name__ == "__main__":
    run()