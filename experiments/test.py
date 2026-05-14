import json

STR = "{\"primary_zone_id\":\"inspiration\",\"zone_ids\":[\"inspiration\",\"parenting\"],\"zone_confidence\":{\"inspiration\":0.8,\"parenting\":0.4},\"reasoning\":\"主分区inspiration，因为用户记录了育儿方法上的新尝试或想法\"}"

a = json.loads(STR)
print(type(a))
b = json.dumps(a, ensure_ascii=False)
print(type(b))
print(b)