from __future__ import annotations
"""
managers/chatbot_manager.py - 챗봇 정의 관리
chatbots/*.json 파일을 읽어 ChatbotDef 객체로 관리한다.
선언형 등록 원칙: JSON 파일 추가/삭제만으로 챗봇을 추가/제거할 수 있다.

3-tier hierarchy 지원 (v2):
- parent_id/level 기반 계층 구조
- 순환 참조 방지 검증
- 최대 깊이 제한 (max_depth=5)
"""
import json
from pathlib import Path
from typing import Optional

from backend.core.models import ChatbotDef
from backend.config import settings


class ChatbotManager:
    # 최대 계층 깊이 (Root=0, Level 5=최대)
    MAX_HIERARCHY_DEPTH = 5
    
    def __init__(self, chatbots_dir: Path | None = None):
        self._dir = chatbots_dir or settings.CHATBOTS_DIR
        self._chatbots: dict[str, ChatbotDef] = {}
        self._load_all()

    # ── 로딩 ──────────────────────────────────────────────────────
    def _load_all(self) -> None:
        self._chatbots.clear()
        for json_file in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                chatbot = ChatbotDef.from_dict(data)
                self._chatbots[chatbot.id] = chatbot
            except Exception as e:
                print(f"[ChatbotManager] {json_file.name} 로드 실패: {e}")
        
        # 로드 후 계층 정보 검증 및 보정
        self._validate_and_fix_hierarchy()

    def reload(self) -> None:
        """런타임 중 챗봇 정의를 다시 불러온다."""
        self._load_all()

    # ── 조회 ──────────────────────────────────────────────────────
    def get(self, chatbot_id: str) -> ChatbotDef | None:
        return self._chatbots.get(chatbot_id)

    def get_active(self, chatbot_id: str) -> ChatbotDef | None:
        chatbot = self._chatbots.get(chatbot_id)
        return chatbot if (chatbot and chatbot.active) else None

    def list_all(self) -> list[ChatbotDef]:
        return list(self._chatbots.values())

    def list_active(self) -> list[ChatbotDef]:
        return [c for c in self._chatbots.values() if c.active]

    # ── 쓰기 (선언형 등록 지원) ─────────────────────────────────
    def save(self, chatbot: ChatbotDef) -> None:
        """챗봇 정의를 JSON 파일로 저장하고 인메모리 상태를 갱신한다."""
        # 계층 구조 검증
        self._validate_hierarchy_on_save(chatbot)
        
        # 부모가 있는 경우 sub_chatbots에 추가
        if chatbot.parent_id:
            parent_file = self._dir / f"{chatbot.parent_id}.json"
            if parent_file.exists():
                parent_data = json.loads(parent_file.read_text(encoding="utf-8"))
                if "sub_chatbots" not in parent_data:
                    parent_data["sub_chatbots"] = []
                # Check if child already exists
                existing_ids = [s.get("id") for s in parent_data["sub_chatbots"] if isinstance(s, dict)]
                if chatbot.id not in existing_ids:
                    parent_data["sub_chatbots"].append({"id": chatbot.id, "level": chatbot.level, "default_role": chatbot.role.value})
                    parent_file.write_text(json.dumps(parent_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        file_path = self._dir / f"{chatbot.id}.json"
        file_path.write_text(json.dumps(chatbot.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._chatbots[chatbot.id] = chatbot

    def delete(self, chatbot_id: str) -> bool:
        """챗봇 정의 파일을 삭제한다. 성공 여부를 반환한다."""
        file_path = self._dir / f"{chatbot_id}.json"
        if file_path.exists():
            file_path.unlink()
            self._chatbots.pop(chatbot_id, None)
            return True
        return False

    # ──────────────────────────────────────────────────────────────
    # 3-tier Hierarchy Support (v2)
    # ──────────────────────────────────────────────────────────────
    
    def get_parent_chain(self, chatbot_id: str) -> list[ChatbotDef]:
        """
        부모 체인을 반환: [root, ..., parent, self]
        Root부터 현재 챗봇까지의 모든 조상을 포함한다.
        """
        chain = []
        visited = set()
        current_id = chatbot_id
        
        # 순환 참조 방지 (max_depth보다 많이 반복하면 중단)
        max_iterations = self.MAX_HIERARCHY_DEPTH + 2
        iteration = 0
        
        while current_id and iteration < max_iterations:
            if current_id in visited:
                # 순환 참조 발견 - 중단
                print(f"[ChatbotManager] 순환 참조 감지: {chatbot_id}")
                break
            
            visited.add(current_id)
            chatbot = self._chatbots.get(current_id)
            if not chatbot:
                break
            
            chain.append(chatbot)
            current_id = chatbot.parent_id
            iteration += 1
        
        # Root부터의 순서로 반환 (뒤집기)
        return list(reversed(chain))
    
    def get_children(self, chatbot_id: str) -> list[ChatbotDef]:
        """
        직계 자식 챗봇들을 반환 (direct children only)
        """
        return [
            c for c in self._chatbots.values()
            if c.parent_id == chatbot_id
        ]
    
    def get_descendants(self, chatbot_id: str) -> list[ChatbotDef]:
        """
        모든 후손 챗봇들을 반환 (recursive, includes children, grandchildren, etc.)
        """
        descendants = []
        to_process = [chatbot_id]
        visited = set()
        
        while to_process:
            current_id = to_process.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)
            
            children = self.get_children(current_id)
            for child in children:
                if child.id not in visited:
                    descendants.append(child)
                    to_process.append(child.id)
        
        return descendants
    
    def get_ancestors(self, chatbot_id: str) -> list[ChatbotDef]:
        """
        모든 조상 챗봇들을 반환 (up to root, excludes self)
        """
        ancestors = []
        visited = set()
        current_id = self._chatbots.get(chatbot_id, {}).parent_id if chatbot_id in self._chatbots else None
        
        # Get the actual parent_id
        if chatbot_id in self._chatbots:
            current_id = self._chatbots[chatbot_id].parent_id
        else:
            return []
        
        max_iterations = self.MAX_HIERARCHY_DEPTH + 2
        iteration = 0
        
        while current_id and iteration < max_iterations:
            if current_id in visited:
                break
            
            visited.add(current_id)
            chatbot = self._chatbots.get(current_id)
            if not chatbot:
                break
            
            ancestors.append(chatbot)
            current_id = chatbot.parent_id
            iteration += 1
        
        # Root가 마지막에 오도록 (현재 -> Root 순서로 수집했으므로 뒤집기)
        return list(reversed(ancestors))
    
    def get_root(self, chatbot_id: str) -> Optional[ChatbotDef]:
        """
        해당 챗봇의 Root 챗봇을 반환
        """
        chain = self.get_parent_chain(chatbot_id)
        return chain[0] if chain else None
    
    def get_tree(self, root_id: Optional[str] = None) -> dict:
        """
        계층 트리 구조를 반환
        
        Args:
            root_id: 특정 Root ID (None이면 모든 Root 챗봉)
        
        Returns:
            {
                'chatbot': ChatbotDef,
                'children': [
                    {'chatbot': ChatbotDef, 'children': [...]},
                    ...
                ]
            }
        """
        if root_id:
            root = self._chatbots.get(root_id)
            if not root:
                return {}
            return self._build_tree_node(root)
        
        # 모든 Root 챗봇 찾기
        roots = [c for c in self._chatbots.values() if c.is_root]
        return {
            'roots': [
                self._build_tree_node(root) for root in roots
            ]
        }
    
    def _build_tree_node(self, chatbot: ChatbotDef) -> dict:
        """재귀적으로 트리 노드 구성"""
        children = self.get_children(chatbot.id)
        return {
            'chatbot': chatbot,
            'children': [self._build_tree_node(child) for child in children]
        }
    
    def _validate_hierarchy_on_save(self, chatbot: ChatbotDef) -> None:
        """
        저장 시 계층 구조 검증
        
        Raises:
            ValueError: 계층 구조 위반 시
        """
        # 1. 순환 참조 검증
        if chatbot.parent_id:
            if self._would_create_cycle(chatbot.id, chatbot.parent_id):
                raise ValueError(
                    f"순환 참조 오류: '{chatbot.id}'의 부모로 '{chatbot.parent_id}'를 설정하면 "
                    f"순환 참조가 발생합니다."
                )
        
        # 2. 최대 깊이 검증
        if chatbot.parent_id:
            parent_chain = self.get_parent_chain(chatbot.parent_id)
            new_depth = len(parent_chain) + 1  # 부모 체인 + 자신
            if new_depth > self.MAX_HIERARCHY_DEPTH:
                raise ValueError(
                    f"최대 깊이 초과: 계층 깊이는 최대 {self.MAX_HIERARCHY_DEPTH}를 "
                    f"초과할 수 없습니다. (현재 깊이: {new_depth})"
                )
        
        # 3. 부모 존재 여부 검증 (신규 챗봇이 아닌 경우)
        if chatbot.parent_id and chatbot.parent_id not in self._chatbots:
            # 새 챗봇 저장 시 부모가 존재해야 함
            # 단, 초기 로딩 시에는 순서 문제로 부모가 없을 수 있음
            pass
    
    def _would_create_cycle(self, chatbot_id: str, potential_parent_id: str) -> bool:
        """
        potential_parent_id를 부모로 설정 시 순환 참조가 발생하는지 검사
        """
        # potential_parent_id의 조상들 중에 chatbot_id가 있는지 확인
        current_id = potential_parent_id
        visited = set()
        max_iterations = self.MAX_HIERARCHY_DEPTH + 2
        iteration = 0
        
        while current_id and iteration < max_iterations:
            if current_id == chatbot_id:
                return True
            if current_id in visited:
                break
            visited.add(current_id)
            
            chatbot = self._chatbots.get(current_id)
            if not chatbot:
                break
            current_id = chatbot.parent_id
            iteration += 1
        
        return False
    
    def _validate_and_fix_hierarchy(self) -> None:
        """
        로드 후 계층 정보 검증 및 자동 보정
        """
        for chatbot in self._chatbots.values():
            # 1. 부모가 없는데 level > 0인 경우 (orphan) -> level 0으로 보정
            if chatbot.parent_id is None and chatbot.level > 0:
                print(f"[ChatbotManager] Warning: '{chatbot.id}'는 부모가 없지만 level={chatbot.level}. "
                      f"level을 0으로 보정합니다.")
                chatbot.level = 0
            
            # 2. 부모가 존재하지 않는 경우 (orphan parent_id)
            if chatbot.parent_id and chatbot.parent_id not in self._chatbots:
                print(f"[ChatbotManager] Warning: '{chatbot.id}'의 부모 '{chatbot.parent_id}'가 존재하지 않습니다. "
                      f"parent_id를 None으로 보정합니다.")
                chatbot.parent_id = None
                chatbot.level = 0
            
            # 3. level이 부모와 일치하지 않는 경우 보정
            if chatbot.parent_id and chatbot.parent_id in self._chatbots:
                parent = self._chatbots[chatbot.parent_id]
                expected_level = parent.level + 1
                if chatbot.level != expected_level:
                    print(f"[ChatbotManager] Warning: '{chatbot.id}'의 level={chatbot.level}이 "
                          f"부모 '{parent.id}'의 level={parent.level}와 일치하지 않습니다. "
                          f"level을 {expected_level}로 보정합니다.")
                    chatbot.level = expected_level

    # ──────────────────────────────────────────────────────────────
    # Utility Methods
    # ──────────────────────────────────────────────────────────────
    
    def get_siblings(self, chatbot_id: str) -> list[ChatbotDef]:
        """
        같은 부모를 가진 형제 챗봇들을 반환 (자신 제외)
        """
        chatbot = self._chatbots.get(chatbot_id)
        if not chatbot or not chatbot.parent_id:
            return []
        
        return [
            c for c in self._chatbots.values()
            if c.parent_id == chatbot.parent_id and c.id != chatbot_id
        ]
    
    def get_leaves(self, root_id: Optional[str] = None) -> list[ChatbotDef]:
        """
        Leaf 노드(자식이 없는 챗봇)들을 반환
        """
        if root_id:
            descendants = self.get_descendants(root_id)
            root = self._chatbots.get(root_id)
            if root:
                descendants.append(root)
            return [d for d in descendants if d.is_leaf]
        
        return [c for c in self._chatbots.values() if c.is_leaf]
