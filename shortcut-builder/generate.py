#!/usr/bin/env python3
# Generate an unsigned Apple Shortcuts workflow (binary plist + editable XML source).
import plistlib, uuid
from pathlib import Path

def uid(): return str(uuid.uuid4()).upper()
actions=[]; questions=[]
def add(kind, **params):
    params.setdefault("UUID", uid())
    actions.append(dict(WFWorkflowActionIdentifier="is.workflow.actions."+kind,
                        WFWorkflowActionParameters=params))
    return params["UUID"]
def magic(uuid, name):
    return {"WFSerializationType":"WFTextTokenAttachment",
            "Value":{"Type":"ActionOutput","OutputUUID":uuid,"OutputName":name}}
def token(item):
    return {"WFSerializationType":"WFTextTokenString",
            "Value":{"string":"\ufffc","attachmentsByRange":{"{0, 1}":item["Value"]}}}
def date_number(uuid,name):
    x=add("format.date",WFDate=token(magic(uuid,name)),WFDateFormatStyle="Custom",
          WFDateFormat="Custom",WFDateFormatString="HHmm",WFLocale="en_US")
    y=add("number",WFNumberActionNumber=magic(x,"Formatted Date"))
    return magic(y,"Number")
def adjust_1h(uuid, name, output_name):
    return add("adjustdate",WFDate=token(magic(uuid,name)),WFAdjustOperation="Subtract",
       WFAdjustOffsetPicker={"WFSerializationType":"WFTimeOffsetValue",
                             "Value":{"Operation":"Subtract","Unit":"Hour","Value":1}},
       WFDuration={"WFSerializationType":"WFQuantityFieldValue",
                   "Value":{"Magnitude":1,"Unit":"hr"}},CustomOutputName=output_name)
def if_beg(left,right):
    g=uid()
    add("conditional",GroupingIdentifier=g,WFControlFlowMode=0,
        WFInput={"Type":"Variable","Variable":left},WFCondition=3,WFNumberValue=right)
    return g
def otherwise(g): add("conditional",GroupingIdentifier=g,WFControlFlowMode=1)
def end(g): add("conditional",GroupingIdentifier=g,WFControlFlowMode=2)
def switch(target): add("posters.switch",WFPoster=target)

add("comment",WFCommentActionText="iOS 18 壁纸智能切换。重要：导入后确认五张墙纸顺序；日出前1小时青绿，08:00蓝，12:00紫，日落前1小时粉，日落后深色。")
all_wallpapers=add("posters.get",WFPosterType="All",CustomOutputName="所有墙纸")
wallpapers={}
for i,(code,color) in enumerate((("green","青绿色"),("blue","蓝色"),("purple","紫色"),("pink","粉色"),("dark","深色")),1):
    index=len(actions)
    a=add("getitemfromlist",WFInput=magic(all_wallpapers,"所有墙纸"),
          WFItemSpecifier="Item At Index",WFItemIndex=i,CustomOutputName=color)
    wallpapers[code]=magic(a,color)
    questions.append({"ActionIndex":index,"Category":"Parameter",
                      "ParameterKey":"WFItemIndex","DefaultValue":i,
                      "Text":color+"壁纸在锁屏墙纸列表中的序号（从1开始）"})

w=add("weather.currentconditions",CustomOutputName="当前天气")
sunrise=add("properties.weather.conditions",WFInput=magic(w,"当前天气"),
            WFContentItemPropertyName="Sunrise Time",CustomOutputName="日出时间")
morning=adjust_1h(sunrise,"日出时间","清晨开始")
sunset=add("properties.weather.conditions",WFInput=magic(w,"当前天气"),
           WFContentItemPropertyName="Sunset Time",CustomOutputName="日落时间")
pink=adjust_1h(sunset,"日落时间","粉色开始")
now=add("date",WFDateActionMode="Current Date",CustomOutputName="现在")
now_n=date_number(now,"现在")
sunset_n=date_number(sunset,"日落时间")
pink_n=date_number(pink,"粉色开始")
morning_n=date_number(morning,"清晨开始")

g=if_beg(now_n,sunset_n)
switch(wallpapers["dark"])
otherwise(g)
g2=if_beg(now_n,pink_n)
switch(wallpapers["pink"])
otherwise(g2)
g3=if_beg(now_n,1200)
switch(wallpapers["purple"])
otherwise(g3)
g4=if_beg(now_n,800)
switch(wallpapers["blue"])
otherwise(g4)
g5=if_beg(now_n,morning_n)
switch(wallpapers["green"])
otherwise(g5)
switch(wallpapers["dark"])
for k in (g5,g4,g3,g2,g): end(k)

wf={"WFWorkflowName":"iOS18智能壁纸（日落前1小时粉色）",
 "WFWorkflowClientVersion":"2602.0.11",
 "WFWorkflowMinimumClientVersion":900,
 "WFWorkflowMinimumClientVersionString":"900",
 "WFWorkflowIcon":{"WFWorkflowIconGlyphNumber":59536,"WFWorkflowIconStartColor":4282601983},
 "WFWorkflowTypes":[],"WFWorkflowInputContentItemClasses":[],
 "WFWorkflowOutputContentItemClasses":[],"WFWorkflowHasOutputFallback":False,
 "WFWorkflowIsDisabledOnLockScreen":False,
 "WFWorkflowImportQuestions":questions,"WFWorkflowActions":actions}
assert len(actions)>40
assert len([x for x in actions if x["WFWorkflowActionIdentifier"].endswith("posters.switch")])==6
assert len([x for x in actions if x["WFWorkflowActionIdentifier"].endswith("adjustdate")])==2
Path("dist").mkdir(exist_ok=True)
Path("dist/iOS18_Smart_Wallpaper_SunsetMinus1h.shortcut").write_bytes(plistlib.dumps(wf,fmt=plistlib.FMT_BINARY))
Path("dist/iOS18_Smart_Wallpaper_SunsetMinus1h.plist").write_bytes(plistlib.dumps(wf,fmt=plistlib.FMT_XML,sort_keys=False))
print("generated actions",len(actions))
