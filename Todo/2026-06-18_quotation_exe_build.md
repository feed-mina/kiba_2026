# 견적서 생성기 exe 빌드·배포 (2026-06-18)

> 목적: Linux 샌드박스에서 만든 견적서 생성기 배포판(zip)을 회사 Windows PC에서 1회 빌드해 exe로 사내 배포합니다.

---

## 1. [빌드] Windows PC에서 exe 생성

**상세 내용:** `견적서생성기_배포판.zip`을 풀고 `build.bat`을 더블클릭하면 PyInstaller가 `dist\견적서생성기.exe`를 만듭니다. 한 번만 빌드하면 됩니다.

**체크리스트:**

- [ ] zip을 적당한 폴더에 풀기(예: `C:\tools\quotation-generator-desktop`).
- [ ] Python 3.9+ 설치 시 "Add Python to PATH" 체크.
- [ ] `build.bat` 더블클릭 → `Successfully installed` / `completed successfully` 메시지 확인.
- [ ] 사내망 설치 실패 시 `--proxy` 또는 `--trusted-host pypi.org --trusted-host files.pythonhosted.org` 사용(개인망 빌드도 대안).
- [ ] `dist\견적서생성기.exe`(15~25MB) 생성 확인.

---

## 2. [검증] exe 동작 확인

**상세 내용:** 배포 전 핵심 기능이 정상인지 점검합니다.

**체크리스트:**

- [ ] exe 더블클릭 시 GUI 창이 뜨는지.
- [ ] `도움말 > 예시 데이터 불러오기`로 샘플 품목이 채워지는지.
- [ ] `엑셀로 저장(바탕화면)`으로 xlsx 생성, 공급가액·세액·합계 자동 계산 확인.

---

## 3. [배포] 사내 전달

**상세 내용:** 검증된 exe 한 파일만 전달하면 받는 PC에는 Python이 필요 없습니다.

**체크리스트:**

- [ ] exe를 메일/USB/공유 드라이브로 직원에게 전달.
- [ ] SmartScreen 경고는 "추가 정보→실행"으로 안내(필요 시 코드 사인 인증서 검토).
- [ ] 백신 오탐 발생 시 예외 처리 또는 `--noupx` 재빌드 안내.

---
