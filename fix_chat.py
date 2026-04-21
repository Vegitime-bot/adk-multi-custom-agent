import re

with open('backend/api/chat.py', 'r') as f:
    content = f.read()

# Replace the if-else block with simple return
old_pattern = r'''    # Agent 모드: 하위 챗봘이 있으면 ParentAgentExecutor 사용
    if chatbot_def\.sub_chatbots:
        return HierarchicalAgentExecutor\(
            chatbot_def, 
            ingestion_client, 
            memory_manager,
            chatbot_manager
        \)
    else:
        return AgentExecutor\(chatbot_def, ingestion_client, memory_manager\)'''

new_code = '''    # Agent 모드: HierarchicalAgentExecutor 사용 (2-tier 위임 지원)
    return HierarchicalAgentExecutor(
        chatbot_def,
        ingestion_client,
        memory_manager,
        chatbot_manager
    )'''

content = re.sub(old_pattern, new_code, content)

with open('backend/api/chat.py', 'w') as f:
    f.write(content)

print("Done!")
