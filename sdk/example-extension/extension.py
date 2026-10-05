def annotate_messages(messages, context):
    kinds={m.get('kind') for m in messages}
    if kinds.intersection({'group_notice','poll','relay'}):
        return {'note':'发现群卡片。建议先核对公告、投票选项或接龙内容；军师没有替你参与。'}
    return {}
