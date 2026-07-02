#!/usr/bin/env bash
set -euo pipefail

OWNER="feed-mina"
REPO="kiba_2026"
PROJECT_ID="PVT_kwHOBc53JM4Ba3_X"
ISSUE44_NODE_ID="I_kwDOS8zux88AAAABG_JDjw"
ISSUE47_NODE_ID="I_kwDOS8zux88AAAABG_6HXw"

echo "== 1) Project Status field/options 조회 =="
FIELDS_JSON="$(gh api graphql -f query='
query($projectId:ID!) {
  node(id:$projectId) {
    ... on ProjectV2 {
      id
      title
      fields(first:50) {
        nodes {
          ... on ProjectV2SingleSelectField {
            id
            name
            options { id name }
          }
        }
      }
    }
  }
}' -F projectId="$PROJECT_ID")"

STATUS_FIELD_ID="$(echo "$FIELDS_JSON" | jq -r '.data.node.fields.nodes[] | select(.name=="Status") | .id')"
INPROGRESS_OPTION_ID="$(echo "$FIELDS_JSON" | jq -r '.data.node.fields.nodes[] | select(.name=="Status") | .options[] | select(.name=="In Progress") | .id')"
DONE_OPTION_ID="$(echo "$FIELDS_JSON" | jq -r '.data.node.fields.nodes[] | select(.name=="Status") | .options[] | select(.name=="Done") | .id')"

if [[ -z "$STATUS_FIELD_ID" || "$STATUS_FIELD_ID" == "null" ]]; then
  echo "ERROR: Status field를 찾지 못했습니다."; exit 1
fi
if [[ -z "$INPROGRESS_OPTION_ID" || "$INPROGRESS_OPTION_ID" == "null" ]]; then
  echo "ERROR: In Progress 옵션을 찾지 못했습니다."; exit 1
fi
if [[ -z "$DONE_OPTION_ID" || "$DONE_OPTION_ID" == "null" ]]; then
  echo "ERROR: Done 옵션을 찾지 못했습니다."; exit 1
fi

echo "STATUS_FIELD_ID=$STATUS_FIELD_ID"
echo "INPROGRESS_OPTION_ID=$INPROGRESS_OPTION_ID"
echo "DONE_OPTION_ID=$DONE_OPTION_ID"

echo
echo "== 2) Project item id(#44,#47) 조회 =="
ITEMS_JSON="$(gh api graphql -f query='
query($projectId:ID!) {
  node(id:$projectId) {
    ... on ProjectV2 {
      items(first:100) {
        nodes {
          id
          content {
            __typename
            ... on Issue { id number title url state }
          }
        }
      }
    }
  }
}' -F projectId="$PROJECT_ID")"

ITEM44_ID="$(echo "$ITEMS_JSON" | jq -r --arg ISSUE_ID "$ISSUE44_NODE_ID" '.data.node.items.nodes[] | select(.content.id==$ISSUE_ID) | .id' | head -n1)"
ITEM47_ID="$(echo "$ITEMS_JSON" | jq -r --arg ISSUE_ID "$ISSUE47_NODE_ID" '.data.node.items.nodes[] | select(.content.id==$ISSUE_ID) | .id' | head -n1)"

if [[ -z "$ITEM44_ID" || "$ITEM44_ID" == "null" ]]; then
  echo "ERROR: #44의 Project item id를 찾지 못했습니다."; exit 1
fi
if [[ -z "$ITEM47_ID" || "$ITEM47_ID" == "null" ]]; then
  echo "ERROR: #47의 Project item id를 찾지 못했습니다."; exit 1
fi

echo "ITEM44_ID=$ITEM44_ID"
echo "ITEM47_ID=$ITEM47_ID"

update_status () {
  local ITEM_ID="$1"
  local OPTION_ID="$2"
  gh api graphql -f query='
mutation($projectId:ID!, $itemId:ID!, $fieldId:ID!, $optionId:String!) {
  updateProjectV2ItemFieldValue(input:{
    projectId:$projectId
    itemId:$itemId
    fieldId:$fieldId
    value:{ singleSelectOptionId:$optionId }
  }) {
    projectV2Item { id }
  }
}' \
-F projectId="$PROJECT_ID" \
-F itemId="$ITEM_ID" \
-F fieldId="$STATUS_FIELD_ID" \
-F optionId="$OPTION_ID" >/dev/null
}

echo
echo "== 3) #44,#47 -> In Progress =="
update_status "$ITEM44_ID" "$INPROGRESS_OPTION_ID"
update_status "$ITEM47_ID" "$INPROGRESS_OPTION_ID"
echo "In Progress 반영 완료"

echo
echo "== 4) 완료 조건 체크(수동 확인) =="
echo "#44, #47 완료 조건을 확인한 뒤 Enter를 누르면 Done으로 변경 + 코멘트 + Close를 진행합니다."
read -r

echo
echo "== 5) #44,#47 -> Done =="
update_status "$ITEM44_ID" "$DONE_OPTION_ID"
update_status "$ITEM47_ID" "$DONE_OPTION_ID"
echo "Done 반영 완료"

echo
echo "== 6) 코멘트 추가 =="
gh issue comment 44 -R "$OWNER/$REPO" --body "Project #3 상태를 In Progress → Done으로 반영했고 완료 기준 충족으로 판단하여 이슈를 종료합니다."
gh issue comment 47 -R "$OWNER/$REPO" --body "Project #3 상태를 In Progress → Done으로 반영했고 완료 기준 충족(운영 OAuth 연결/검증 완료)으로 판단하여 이슈를 종료합니다."
echo "코멘트 완료"

echo
echo "== 7) 이슈 Close =="
gh issue close 44 -R "$OWNER/$REPO"
gh issue close 47 -R "$OWNER/$REPO"
echo "Close 완료"

echo
echo "== 8) 최종 검증 =="
gh issue view 44 -R "$OWNER/$REPO" --json number,state,title,url
gh issue view 47 -R "$OWNER/$REPO" --json number,state,title,url

echo
echo "모든 작업 완료 ✅"