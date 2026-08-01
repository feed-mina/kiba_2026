# GitHub Projects v2 setup

이 저장소는 새 GitHub Issue를 Project v2에 자동으로 추가할 수 있습니다.

## 설정

1. Projects 읽기·쓰기 권한을 가진 fine-grained personal access token을 만듭니다.
2. 저장소 secret `ADD_TO_PROJECT_PAT`에 토큰을 등록합니다.
3. 저장소 variable `PROJECT_URL`에 Project URL을 등록합니다.

```bash
gh secret set ADD_TO_PROJECT_PAT --repo OWNER/REPOSITORY
gh variable set PROJECT_URL --repo OWNER/REPOSITORY \
  --body "https://github.com/users/OWNER/projects/PROJECT_NUMBER"
```

새 Project가 필요하면 다음과 같이 생성하고 저장소에 연결합니다.

```bash
gh project create --owner OWNER --title "Project Operations"
gh project link PROJECT_NUMBER --owner OWNER --repo REPOSITORY
```

기존 open Issue는 `project-backfill.yml`을 수동 실행해 추가합니다.

```bash
gh workflow run project-backfill.yml --repo OWNER/REPOSITORY -f state=open
```

이후 새 Issue는 `add-to-project.yml`이 자동으로 추가합니다.
