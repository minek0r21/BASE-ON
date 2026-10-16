"""
오류 응답 형식 (API 명세 공통 규칙):
{"error": {"code": "PLAYER_NOT_FOUND", "message": "선수를 찾을 수 없습니다"}}
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):  # 오류 정보(상태코드, 코드, 메시지) 담기
        self.status, self.code, self.message = status, code, message


def _body(code, message):  # 오류 JSON 모양 만들기
    return {"error": {"code": code, "message": message}}


def register(app: FastAPI):  # 아래 오류 처리기 3개를 앱에 등록
    @app.exception_handler(ApiError)
    async def api_error(_: Request, e: ApiError):  # 우리가 낸 오류(ApiError) → 정해진 형식
        return JSONResponse(_body(e.code, e.message), status_code=e.status)

    # 쿼리 파라미터가 잘못됐을 때 (예: season=abc) FastAPI 기본 422 대신 400
    @app.exception_handler(RequestValidationError)
    async def bad_request(_: Request, e: RequestValidationError):  # 잘못된 파라미터 → 400 INVALID_PARAM
        first = e.errors()[0]
        where = ".".join(str(x) for x in first["loc"][1:])
        return JSONResponse(_body("INVALID_PARAM", f"잘못된 값: {where}"), status_code=400)

    @app.exception_handler(Exception)
    async def server_error(_: Request, e: Exception):  # 예상 못 한 오류 → 500 SERVER_ERROR
        return JSONResponse(_body("SERVER_ERROR", "서버 오류가 발생했습니다"), status_code=500)
