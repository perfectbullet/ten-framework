"""
天气查询工具（同步版本 + 中文拼音支持）
Author: perfectbullet
Date: 2025-11-19 11:27:43 UTC
"""

import httpx
from pypinyin import lazy_pinyin
import re

# ---------------------------------------------------------------------------
# Weather helpers
# ---------------------------------------------------------------------------
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
DEFAULT_UNITS = "metric"  # use Celsius by default
DEFAULT_LANG = "zh_cn"  # Chinese descriptions

# 常见城市名称映射（可选，用于特殊情况）
CITY_NAME_MAP = {
    # 直辖市
    "北京": "Beijing",
    "上海": "Shanghai",
    "天津": "Tianjin",
    "重庆": "Chongqing",
    
    # 省会城市
    "广州": "Guangzhou",
    "深圳": "Shenzhen",
    "成都": "Chengdu",
    "杭州": "Hangzhou",
    "武汉": "Wuhan",
    "西安": "Xi'an",
    "南京": "Nanjing",
    "郑州": "Zhengzhou",
    "长沙": "Changsha",
    "沈阳": "Shenyang",
    "青岛": "Qingdao",
    "大连": "Dalian",
    "厦门": "Xiamen",
    "济南": "Jinan",
    "哈尔滨": "Harbin",
    "长春": "Changchun",
    "福州": "Fuzhou",
    "石家庄": "Shijiazhuang",
    "合肥": "Hefei",
    "南昌": "Nanchang",
    "昆明": "Kunming",
    "太原": "Taiyuan",
    "贵阳": "Guiyang",
    "南宁": "Nanning",
    "兰州": "Lanzhou",
    "海口": "Haikou",
    "银川": "Yinchuan",
    "西宁": "Xining",
    "呼和浩特": "Hohhot",
    "乌鲁木齐": "Urumqi",
    "拉萨": "Lhasa",
    
    # 特别行政区
    "香港": "Hong Kong",
    "澳门": "Macao",
    
    # 台湾主要城市
    "台北": "Taipei",
    "高雄": "Kaohsiung",
}


def is_chinese(text: str) -> bool:
    """
    判断字符串是否包含中文字符
    
    Args:
        text: 输入字符串
        
    Returns:
        如果包含中文返回 True，否则返回 False
    """
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def convert_city_to_pinyin(city: str) -> str:
    """
    将中文城市名转换为拼音（首字母大写）
    
    Args:
        city: 城市名称（中文或拼音）
        
    Returns:
        拼音城市名称
    """
    # 如果不包含中文，直接返回
    if not is_chinese(city):
        return city
    
    # 优先使用预定义的映射（更准确）
    if city in CITY_NAME_MAP:
        return CITY_NAME_MAP[city]
    
    # 使用 pypinyin 自动转换
    pinyin_list = lazy_pinyin(city)
    # 首字母大写，其余小写
    pinyin = ''.join(word.capitalize() for word in pinyin_list)
    
    return pinyin


def fetch_weather(city: str, api_key: str) -> dict[str, str]:
    """
    调用 OpenWeather API 并返回简化的天气信息字典（同步版本）
    
    Args:
        city: 城市名称（支持中文和拼音）
        api_key: OpenWeather API Key
        
    Returns:
        包含天气信息的字典
        
    Raises:
        httpx.HTTPStatusError: 如果响应状态码非 2xx
    """
    os.environ.setdefault('DASHSCOPE_API_KEY', 'sk-8d2c6b34857f4dfc84bb797bffe265ab')

    # 保存原始城市名（用于显示）
    original_city = city
    
    # 转换为拼音（OpenWeather API 需要）
    city_pinyin = convert_city_to_pinyin(city)
    
    print(f"🔄 城市名转换: {original_city} → {city_pinyin}")
    
    params = {
        "q": city_pinyin,  # 使用拼音
        "appid": api_key,
        "units": DEFAULT_UNITS,
        "lang": DEFAULT_LANG,
    }
    
    # 使用同步客户端
    with httpx.Client(timeout=10) as client:
        r = client.get(OPENWEATHER_URL, params=params)
        r.raise_for_status()
        data = r.json()
    
    # 提取简洁的摘要信息
    weather_main = data["weather"][0]["main"]
    description = data["weather"][0]["description"]
    temp = data["main"]["temp"]
    feels_like = data["main"]["feels_like"]
    humidity = data["main"]["humidity"]
    
    weather = {
        "city": original_city,  # 使用原始城市名（中文或拼音）
        "city_pinyin": city_pinyin,  # 添加拼音版本
        "weather": weather_main,
        "description": description,
        "temp": f"{temp}°C",
        "feels_like": f"{feels_like}°C",
        "humidity": f"{humidity}%",
    }
    
    # 组合人类可读的摘要
    summary = (
        f"{weather['city']}：{weather['description']}，温度 {weather['temp']}，"
        f"体感 {weather['feels_like']}，湿度 {weather['humidity']}。"
    )
    
    # 添加摘要到返回字典
    weather["summary"] = summary
    
    return weather


def main():
    """主函数：测试天气查询"""
    
    print("🌤️  天气查询工具（支持中文/拼音）")
    print(f"👤 用户: perfectbullet")
    print(f"📅 日期: 2025-11-19 11:27:43 UTC\n")
    
    api_key = "8d78f7c5c23210915f3d1a6863cb5175"
    
    # 测试中文城市名
    print("="*70)
    print("测试 1: 使用中文城市名")
    print("="*70)
    
    chinese_cities = ["北京", "上海", "深圳", "广州"]
    
    for city in chinese_cities:
        try:
            weather = fetch_weather(city=city, api_key=api_key)
            print(f"\n✅ {weather['summary']}")
        except httpx.HTTPStatusError as e:
            print(f"\n❌ {city}: HTTP 错误 {e.response.status_code}")
            print(f"   响应: {e.response.text}")
        except Exception as e:
            print(f"\n❌ {city}: {e}")
    
    # 测试拼音城市名
    print("\n" + "="*70)
    print("测试 2: 使用拼音城市名")
    print("="*70)
    
    pinyin_cities = ["Beijing", "Shanghai", "Chengdu", "Hangzhou"]
    
    for city in pinyin_cities:
        try:
            weather = fetch_weather(city=city, api_key=api_key)
            print(f"\n✅ {weather['summary']}")
        except Exception as e:
            print(f"\n❌ {city}: {e}")
    
    # 测试混合
    print("\n" + "="*70)
    print("测试 3: 混合使用")
    print("="*70)
    
    mixed_cities = ["西安", "Wuhan", "厦门", "Qingdao"]
    
    for city in mixed_cities:
        try:
            weather = fetch_weather(city=city, api_key=api_key)
            print(f"\n✅ {weather['summary']}")
        except Exception as e:
            print(f"\n❌ {city}: {e}")
    
    # 测试特殊城市（香港、澳门等）
    print("\n" + "="*70)
    print("测试 4: 特殊地区")
    print("="*70)
    
    special_cities = ["香港", "澳门", "台北"]
    
    for city in special_cities:
        try:
            weather = fetch_weather(city=city, api_key=api_key)
            print(f"\n✅ {weather['summary']}")
        except Exception as e:
            print(f"\n❌ {city}: {e}")


if __name__ == '__main__':
    main()