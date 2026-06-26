"""Rebuild src/data/cities.json from china_admin.gpkg."""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import geopandas as gpd
except ImportError:
    print("pip install geopandas", file=sys.stderr)
    sys.exit(1)

# Province name → English mapping
_PROV_EN: dict[str, str] = {
    "北京市": "Beijing", "天津市": "Tianjin", "上海市": "Shanghai", "重庆市": "Chongqing",
    "河北省": "Hebei", "山西省": "Shanxi", "内蒙古自治区": "Inner Mongolia",
    "辽宁省": "Liaoning", "吉林省": "Jilin", "黑龙江省": "Heilongjiang",
    "江苏省": "Jiangsu", "浙江省": "Zhejiang", "安徽省": "Anhui",
    "福建省": "Fujian", "江西省": "Jiangxi", "山东省": "Shandong",
    "河南省": "Henan", "湖北省": "Hubei", "湖南省": "Hunan",
    "广东省": "Guangdong", "广西壮族自治区": "Guangxi", "海南省": "Hainan",
    "四川省": "Sichuan", "贵州省": "Guizhou", "云南省": "Yunnan",
    "西藏自治区": "Tibet", "陕西省": "Shaanxi", "甘肃省": "Gansu",
    "青海省": "Qinghai", "宁夏回族自治区": "Ningxia",
    "新疆维吾尔自治区": "Xinjiang", "香港特别行政区": "Hong Kong",
    "澳门特别行政区": "Macao", "台湾省": "Taiwan",
}

# City name → English mapping for major cities
_CITY_EN: dict[str, str] = {
    "北京市": "Beijing", "天津市": "Tianjin", "上海市": "Shanghai", "重庆市": "Chongqing",
    "石家庄市": "Shijiazhuang", "唐山市": "Tangshan", "秦皇岛市": "Qinhuangdao",
    "邯郸市": "Handan", "邢台市": "Xingtai", "保定市": "Baoding",
    "张家口市": "Zhangjiakou", "承德市": "Chengde", "沧州市": "Cangzhou",
    "廊坊市": "Langfang", "衡水市": "Hengshui", "太原市": "Taiyuan",
    "大同市": "Datong", "沈阳市": "Shenyang", "大连市": "Dalian",
    "长春市": "Changchun", "吉林市": "Jilin", "哈尔滨市": "Harbin",
    "南京市": "Nanjing", "苏州市": "Suzhou", "无锡市": "Wuxi",
    "杭州市": "Hangzhou", "宁波市": "Ningbo", "温州市": "Wenzhou",
    "合肥市": "Hefei", "福州市": "Fuzhou", "厦门市": "Xiamen",
    "南昌市": "Nanchang", "济南市": "Jinan", "青岛市": "Qingdao",
    "郑州市": "Zhengzhou", "武汉市": "Wuhan", "长沙市": "Changsha",
    "广州市": "Guangzhou", "深圳市": "Shenzhen", "珠海市": "Zhuhai",
    "南宁市": "Nanning", "海口市": "Haikou", "三亚市": "Sanya",
    "成都市": "Chengdu", "贵阳市": "Guiyang", "昆明市": "Kunming",
    "拉萨市": "Lhasa", "西安市": "Xi'an", "兰州市": "Lanzhou",
    "西宁市": "Xining", "银川市": "Yinchuan", "乌鲁木齐市": "Urumqi",
    "呼和浩特市": "Hohhot", "长沙市": "Changsha",
    # Direct-controlled municipality districts
    "东城区": "Dongcheng", "西城区": "Xicheng", "朝阳区": "Chaoyang",
    "丰台区": "Fengtai", "石景山区": "Shijingshan", "海淀区": "Haidian",
    "门头沟区": "Mentougou", "房山区": "Fangshan", "通州区": "Tongzhou",
    "顺义区": "Shunyi", "昌平区": "Changping", "大兴区": "Daxing",
    "怀柔区": "Huairou", "平谷区": "Pinggu", "密云区": "Miyun",
    "延庆区": "Yanqing", "和平区": "Heping", "河东区": "Hedong",
    "河西区": "Hexi", "南开区": "Nankai", "河北区": "Hebei District",
    "红桥区": "Hongqiao", "滨海新区": "Binhai New Area", "武清区": "Wuqing",
    "宝坻区": "Baodi", "静海区": "Jinghai", "宁河区": "Ninghe",
    "蓟州区": "Jizhou", "黄浦区": "Huangpu", "徐汇区": "Xuhui",
    "长宁区": "Changning", "静安区": "Jing'an", "普陀区": "Putuo",
    "虹口区": "Hongkou", "杨浦区": "Yangpu", "闵行区": "Minhang",
    "宝山区": "Baoshan", "嘉定区": "Jiading", "浦东新区": "Pudong",
    "金山区": "Jinshan", "松江区": "Songjiang", "青浦区": "Qingpu",
    "奉贤区": "Fengxian", "崇明区": "Chongming",
}

_PROVINCE_CENTERS: dict[str, list[float]] = {
    "110000": [116.407526, 39.904030], "120000": [117.200983, 39.084158],
    "130000": [114.502461, 38.045474], "140000": [112.549248, 37.857014],
    "150000": [111.670801, 40.818311], "210000": [123.429096, 41.796767],
    "220000": [125.324501, 43.886841], "230000": [126.642464, 45.756967],
    "310000": [121.472644, 31.231706], "320000": [118.767413, 32.041544],
    "330000": [120.153576, 30.287459], "340000": [117.283042, 31.861191],
    "350000": [119.306239, 26.075302], "360000": [115.892151, 28.676493],
    "370000": [117.000923, 36.675807], "410000": [113.665412, 34.757975],
    "420000": [114.298572, 30.584355], "430000": [112.982279, 28.19409],
    "440000": [113.280637, 23.125178], "450000": [108.320004, 22.82402],
    "460000": [110.33119, 20.031971], "500000": [106.551556, 29.563009],
    "510000": [104.065735, 30.659462], "520000": [106.713478, 26.578343],
    "530000": [102.712251, 25.040609], "540000": [91.132212, 29.660361],
    "610000": [108.948024, 34.263161], "620000": [103.823557, 36.058039],
    "630000": [101.778916, 36.623178], "640000": [106.278179, 38.46637],
    "650000": [87.617733, 43.792818], "710000": [121.509062, 25.044332],
    "810000": [114.173355, 22.320048], "820000": [113.54909, 22.198745],
}


def build_cities_json(gpkg_path: Path, output: Path) -> None:
    prov_gdf = gpd.read_file(gpkg_path, layer="province")
    city_gdf = gpd.read_file(gpkg_path, layer="city")

    provinces = []
    for _, prow in prov_gdf.iterrows():
        padcode = prow["adcode"]
        pname = prow["name"]
        pname_en = _PROV_EN.get(pname, "")

        # Use hardcoded center or compute from geometry centroid
        if padcode in _PROVINCE_CENTERS:
            pcenter = _PROVINCE_CENTERS[padcode]
        else:
            c = prow.geometry.centroid
            pcenter = [round(c.x, 6), round(c.y, 6)]

        # Get cities for this province
        pcities = city_gdf[city_gdf["province_adcode"] == padcode].copy()
        cities = []
        for _, crow in pcities.iterrows():
            cadcode = crow["adcode"]
            cname = crow["name"]
            cname_en = _CITY_EN.get(cname, "")
            c = crow.geometry.centroid
            cities.append({
                "adcode": cadcode,
                "name": cname,
                "name_en": cname_en,
                "center": [round(c.x, 6), round(c.y, 6)],
            })

        # Sort by adcode
        cities.sort(key=lambda x: x["adcode"])

        provinces.append({
            "adcode": padcode,
            "name": pname,
            "name_en": pname_en,
            "center": pcenter,
            "cities": cities,
        })

    provinces.sort(key=lambda x: x["adcode"])

    data = {"provinces": provinces}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    total_cities = sum(len(p["cities"]) for p in provinces)
    print(f"[OK] {len(provinces)} 个省份，共 {total_cities} 个城市/区 → {output}")


if __name__ == "__main__":
    base = Path(__file__).parent.parent
    build_cities_json(
        base / "src" / "data" / "china_admin.gpkg",
        base / "src" / "data" / "cities.json",
    )
