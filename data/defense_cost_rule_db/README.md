# 방산원가 규칙 조문 DB화 산출물

`docs/원가계산보고서샘플/방산원가대상물자의 원가계산에 관한 규칙(국방부령)(제01202호)(20260130).pdf`를
`(E)sample_원가계산보고서ver2.xlsx.xlsx` 및 기존 `sample_ver1_cost_db/ver2` 도메인 테이블과 연결하기 위한 작업 폴더입니다.

## 파일

- `legal_articles.json`: PDF에서 추출한 장/절/조문/정의 seed.
- `article_excel_mapping.json`: 주요 조문을 Excel 시트, DB 테이블, DDD 객체에 연결한 초안.
- `source_comparison.json`: PDF와 Excel/ver2 DB의 구조 비교 요약.
- `schema.sql`: 기존 원가계산 DB에 법령 조문 근거를 연결하기 위한 PostgreSQL 확장 스키마 초안.
- `policy_article_links.json`: 기존 ver2 `calculation_policy`와 방산 조문 연결 seed 후보.
- `policy_article_links.sql`: `legal_calculation_policy_link` insert SQL 후보.
- `policy_link_check.json`: 조문-정책 링크 검증 결과.
- `../../docs/원가계산보고서샘플/방산원가_조문_DB_뷰.html`: 조문/매핑/정책 링크를 확인하는 정적 HTML 뷰.

## 재생성

```powershell
python .\scripts\analyze_defense_cost_rule_sources.py
python .\scripts\generate_defense_rule_policy_links.py
python .\scripts\verify_defense_rule_policy_links.py
python .\scripts\build_defense_rule_db_view.py
```

## 현재 결론

- PDF는 규칙/근거 원천이고, Excel은 특정 원가계산 인스턴스다.
- ver2 Excel은 기존 DB 후보 계산값과 `원가계산서!E34 = 109,104,460`, `결과!J10 = 109,104,460`이 일치한다.
- 조문 DB는 기존 `calculation_policy`, `rate_rule`, `cost_total_component`, `cost_line`에 직접 섞기보다 `legal_*` 테이블로 분리해 연결하는 편이 안전하다.
- 기존 ver2 계산정책 11개 중 8개는 제6조/제23조/제24조/제26조에 연결 가능하고, 3개는 VAT/천단위 절사/결과표 표시 정책으로 분리하는 것이 맞다.
- 조문-정책 링크 검증은 통과했다. 연결 정책 8개, 분리 정책 3개, 문제 0개.
- 정적 HTML 뷰는 별도 서버 없이 브라우저에서 열 수 있다.
