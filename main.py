import json, time, os, re, csv, click
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from rich.console import Console
from rich.table import Table
from rich.layout import Layout

header = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36',
    'Referer': 'http://www.weather.com.cn/'
}

def get(url):
    res = requests.get(url, headers=header)
    res.encoding = 'utf-8' #TIL
    return res

def get_hour3(bs):
    s1 = bs.select('#today script')[0]
    # $('body script[src*="hour3data"]')[0]
    hour3data = json.loads(s1.string[len('var hour3data=')+1:])
    data = [e.split(',') for pack in hour3data['7d'] for e in pack]
    # 获取起始时间
    day, hour = re.match('(\d+)日(\d+)时', data[0][0]).groups()
    base_date = datetime.now().replace(hour=int(hour), minute=0, second=0, microsecond=0)

    res = []
    for i in range(len(data)):
        _, _, weather, temperature, direction, strength, _ = data[i]
        temperature = temperature[:-1]
        # 风力强度改成区间
        strength = re.match('(\d+)-(\d+)', strength.replace('<', '0-')).groups()
        strength = list(map(lambda e: int(e), strength))
        res.append((base_date + timedelta(hours=i*3), weather, temperature, direction, strength[0], strength[1]))
    return res

keymap = {
    'od21': 'hour',
    'od22': 'temperature', 
    'od23': 'direction_angel',
    'od24': 'direction',
    'od25': 'strength',
    'od26': 'rain', # 降雨量 mm
    'od27': 'humidity', # %
    'od28': 'unknown'
}
def rename_keys(data, keymap):
    keys = list(data.keys())
    for k in keys:
        if k in keymap:
            data[keymap[k]] = data[k]
            del data[k]
    return data

def get_observer24(bs):
    s2 = bs.select('div.left-div script')[1]
    observe24h_data = json.loads(s2.string[len('var observe24h_data =')+1:-2])
    od = observe24h_data['od']

    data = [rename_keys(e, keymap) for e in od['od2']]
    # 原数据的时间是倒序的
    data.reverse()

    hour = data[0]['hour']
    base_date = datetime.now().replace(hour=int(hour), minute=0, second=0, microsecond=0)
    keys = ['temperature', 'direction_angel', 'strength', 'rain', 'humidity']
    for i in range(len(data)):
        e = data[i]
        e['time'] = base_date + timedelta(hours=i)
        for k in keys:
            e[k] = int(e[k])

        del e['unknown']
        del e['hour']
    return data


def get_city_list():
    #get_weather(101010200)
    res = get('https://j.i8tq.com/weather2020/search/city.js')
    city_data = json.loads(res.text[len('var city_data ='):])
    with open('city.json', 'w') as f: json.dump(city_data, f)

def iterate_city(city, parent=[]):
    for k in city:
        if 'AREAID' not in city[k]:
            nParent = parent+[k] if k not in parent else parent
            for c in iterate_city(city[k], nParent):
                yield c
        else:
            if parent[-1] == k:
                nParent = parent[:-1]
            else:
                nParent = parent

            city[k]['PARENT'] = nParent[-1] if len(nParent) else None
            yield city[k]

def get_weather(city_id):
    res = get(f'http://www.weather.com.cn/weather1d/{city_id}.shtml')
    bs = BeautifulSoup(res.text, 'html.parser')

    ts = datetime.now().strftime('%Y-%m-%dT%H%M%S')
    days7 = get_hour3(bs)
    #with open(f'{city_id}_{ts}_day7.csv', 'w', newline='') as csvfile:
    #    writer = csv.writer(csvfile)
    #    writer.writerow(['time', 'weather', 'temperature', 'direction', 'strength_from', 'strength_to'])
    #    for e in days7:
    #        writer.writerow(e)

    #hours24 = get_observer24(bs)
    #with open(f'{city_id}_{ts}_hours24.csv', 'w', newline='') as csvfile:
    #    fieldnames = ['time', 'temperature', 'direction', 'strength', 'direction_angel', 'rain', 'humidity']
    #    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

    #    writer.writeheader()
    #    for e in hours24:
    #        writer.writerow(e)
    return days7, hours24

def search_city(city_name = None):
    if not os.path.exists('./city.json'):
        get_city_list()

    with open('./city.json') as f:
        city = json.load(f)
    name_area = {}
    for c in iterate_city(city, ['中国']):
        name_area[c['NAMECN']] = c
    if city_name == None:
        return name_area

    return name_area[city_name] if city_name in name_area else None

def group_by_day(data):
    days = {}
    for e in data:
        time = e[0].replace(hour=0)
        if time not in days:
            days[time] = []
        days[time].append(e)
    return days

def aggregate(data):
    return {
            'date': data[0][0].strftime('%Y%m%d'),
            'weather0': data[0][1],
            'weather1': data[-1][1],
            'min_temp': min([e[2] for e in data]),
            'max_temp': max([e[2] for e in data]),
            'min_wind': min([e[4] for e in data]),
            'max_wind': min([e[5] for e in data])
    }
@click.group()
def cli():
    pass

@cli.command()
@click.argument('city')
def query(city):
    config = search_city(city)
    if config == None:
        return print("找不到城市 " + city)
    days7, hours24 = get_weather(config['AREAID'])

    table7 = Table(title=f"{city}近7天天气")

    table7.add_column("日期", justify="right", style="cyan", no_wrap=True)
    table7.add_column("天气", justify='center', style="magenta")
    table7.add_column("温度", justify="right", style="green")
    table7.add_column("风力", justify="right", style="green")

    for d in map(aggregate, group_by_day(days7).values()):
        if d['weather0'] == d['weather1']:
            weather = d['weather0']
        else:
            weather = f"{d['weather0']}转{d['weather1']}"
        temperature = f'{d["min_temp"]}~{d["max_temp"]}'
        wind = f'{d["min_wind"]}~{d["max_wind"]}'

        table7.add_row(d['date'], weather, temperature, wind)


    table24 = Table(title=f"{city}近24小时天气")

    table24.add_column("时间",   justify="right", style="cyan", no_wrap=True)
    table24.add_column("温度",   justify='center', style="green")
    table24.add_column("湿度",   justify='center', style="green")
    table24.add_column("风力",   justify="center", style="green")
    table24.add_column("降雨量", justify="center", style="red")

    for d in hours24:
        table24.add_row(
                d['time'].strftime('%Y%m%d'), 
                str(d['temperature']), str(d['humidity']), 
                str(d['strength']), str(d['rain']))

    console = Console()
    layout = Layout()
    layout.split(
        Layout(table24, name="left"),
        Layout(table7, name="right"),
        direction="horizontal"
    )
    layout.height = 30
    console.print(layout)
    

@cli.command()
@click.argument('city', default='')
def scrape(city):
    click.echo('scraping'+ city)

if __name__ == '__main__':
    cli()