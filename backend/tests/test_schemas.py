"""schemas 数据契约测试。

不碰网络、不碰 LLM —— 只验证 Pydantic 模型自身的解析与校验行为。
"""

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    Attraction,
    POIInfo,
    TripPlan,
    TripRequest,
    WeatherInfo,
)


class TestTripRequest:
    def test_valid_request(self):
        req = TripRequest(
            city="杭州",
            start_date="2026-10-20",
            end_date="2026-10-22",
            travel_days=3,
            transportation="公共交通",
            accommodation="经济型酒店",
        )
        assert req.city == "杭州"
        assert req.preferences == []  # 默认值
        assert req.free_text_input == ""  # 默认值

    def test_travel_days_out_of_range_rejected(self):
        # travel_days 有 ge=1 le=30 约束，越界必须在入口被 422 拦下
        with pytest.raises(ValidationError):
            TripRequest(
                city="杭州",
                start_date="2026-10-20",
                end_date="2026-11-20",
                travel_days=0,
                transportation="公共交通",
                accommodation="经济型酒店",
            )
        with pytest.raises(ValidationError):
            TripRequest(
                city="杭州",
                start_date="2026-10-20",
                end_date="2026-11-20",
                travel_days=31,
                transportation="公共交通",
                accommodation="经济型酒店",
            )


class TestWeatherInfo:
    def test_parse_temperature_strips_unit(self):
        w = WeatherInfo(date="2026-10-20", day_temp="22°C", night_temp="15℃")
        assert w.day_temp == 22
        assert w.night_temp == 15

    def test_parse_temperature_garbage_becomes_zero(self):
        # LLM 返回 "22-28" 这类解析不了的值时回落 0，而不是抛异常炸掉整个计划
        w = WeatherInfo(date="2026-10-20", day_temp="22-28", night_temp="abc")
        assert w.day_temp == 0
        assert w.night_temp == 0

    def test_parse_temperature_keeps_int(self):
        w = WeatherInfo(date="2026-10-20", day_temp=18, night_temp=9)
        assert w.day_temp == 18
        assert w.night_temp == 9


class TestAttraction:
    def test_location_optional_when_missing(self):
        # 降级路径：坐标缺失时宁可留空，也不能逼着模型编一个
        a = Attraction(name="西湖", address="杭州市西湖区", visit_duration=120, description="湖")
        assert a.location is None

    def test_location_present(self):
        a = Attraction(
            name="西湖",
            address="杭州市西湖区",
            visit_duration=120,
            description="湖",
            location={"longitude": 120.14, "latitude": 30.25},
        )
        assert a.location.longitude == pytest.approx(120.14)


class TestPOIInfo:
    def test_search_result_without_location(self):
        # 高德 maps_text_search 不返回坐标，POIInfo 必须允许 location 缺失
        poi = POIInfo(id="B000A8UIN8", name="故宫博物院")
        assert poi.location is None
        assert poi.address == ""  # 默认空串，不报错


class TestTripPlan:
    def test_fallback_fields_default_false(self):
        plan = TripPlan(
            city="杭州",
            start_date="2026-10-20",
            end_date="2026-10-21",
            days=[],
            overall_suggestions="建议",
        )
        assert plan.is_fallback is False
        assert plan.fallback_reason is None
        assert plan.weather_info == []

    def test_fallback_fields_roundtrip(self):
        plan = TripPlan(
            city="杭州",
            start_date="2026-10-20",
            end_date="2026-10-21",
            days=[],
            overall_suggestions="占位",
            is_fallback=True,
            fallback_reason="HelloAgentsException",
        )
        # 前端契约：is_fallback 必须能原样序列化回 JSON
        assert plan.model_dump()["is_fallback"] is True
