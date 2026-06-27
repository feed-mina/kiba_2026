# 3개 입력 엑셀 기반 원가계산서 생성기

GitHub Issue: https://github.com/feed-mina/kiba_2026/issues/41

`sample_ver1`, `sample_ver2` 원가계산보고서 형식을 기준으로 `단가대비표`, `내역서`, `집계표` 3개 Excel 파일을 받아 원가계산서 workbook을 생성하는 MVP다.

## 생성 방식

- 템플릿 workbook은 기존 sample 원가계산보고서를 사용한다.
- 입력 workbook에서 `단가대비표`, `내역서`, `집계표` 시트를 찾는다.
- 템플릿 workbook의 같은 이름 시트에 입력 시트의 cell data를 주입한다.
- 템플릿의 `원가계산서`, `결과`, 보조 산출표, 수식 체인은 유지한다.
- workbook 계산 속성을 `auto`, `fullCalcOnLoad`, `forceFullCalc`로 설정해 Excel에서 열 때 재계산되도록 한다.

## CLI

```powershell
& "C:\Users\Samsung\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" `
  scripts\build_cost_statement_workbook.py `
  --price-comparison "path\to\단가대비표.xlsx" `
  --detail "path\to\내역서.xlsx" `
  --summary "path\to\집계표.xlsx" `
  --output "outputs\issue41\generated_원가계산서.xlsx" `
  --template-version ver1
```

`--template-version ver2`를 지정하면 sample_ver2 템플릿을 사용한다. 운영 템플릿 파일을 직접 지정하려면 `--template "path\to\template.xlsx"`를 사용한다.

## Sample smoke test

현재는 독립된 3개 입력 파일 대신 sample workbook 한 개를 세 입력 역할에 반복 지정해 round-trip을 검증했다.

| 템플릿 | 출력 파일 | 최종 총액 | 검증 |
| --- | --- | ---: | --- |
| ver1 | `outputs/issue41/sample_ver1_generated_원가계산서.xlsx` | 123,387,460 | `checks=2/2`, `comparisons=1/1`, diff `0` |
| ver2 | `outputs/issue41/sample_ver2_generated_원가계산서.xlsx` | 109,104,460 | `checks=2/2`, `comparisons=1/1`, diff `0` |

## 남은 확인

- 실제 분리된 `단가대비표.xlsx`, `내역서.xlsx`, `집계표.xlsx` 입력 파일로 end-to-end 검증한다.
- 입력 시트의 서식/병합/인쇄영역을 출력 workbook에 그대로 복사할지 결정한다.
- Excel 없이 서버에서 계산값까지 갱신해야 하면 LibreOffice headless 또는 Excel COM 재계산 단계를 추가한다.
- 웹 UI 업로드/다운로드 흐름으로 연결한다.
