"""Illustrative arithmetic scenarios, not predictions or proof of available content."""
from fractions import Fraction
from progression_reference import level_for_xp, chronicles

def run(name, counts, quality, repeats, avg_repeat_xp, reader_volumes, diagnostic_volumes, seals):
    gross = counts[0]*40 + counts[1]*80 + counts[2]*120
    raw = gross*Fraction(str(quality)); primary = raw.numerator//raw.denominator
    theory = reader_volumes*84 + diagnostic_volumes*12
    bonus = sum(n*p for n,p in zip(seals, [40,80,80,160,200]))
    total = primary + repeats*avg_repeat_xp + theory + bonus
    return {"scenario":name,"primary":primary,"repeats":repeats*avg_repeat_xp,"theory":theory,"seals":bonus,"total":total,"level":level_for_xp(total),"chronicles":chronicles(total)}

def main():
    scenarios=[run("conservative",(80,90,10),.80,80,20,12,5,(17,15,8,2,0)),run("baseline",(70,150,30),.95,150,26,20,5,(25,25,25,5,3)),run("intensive",(40,190,60),.98,170,27,10,15,(25,25,25,5,3))]
    import json
    print(json.dumps({"warning":"Static arithmetic only; content availability and time-to-complete unverified. Average repeat amounts are scenario inputs, not tariffs.","scenarios":scenarios},ensure_ascii=False,indent=2))
    assert scenarios[1]["total"] == 29520 and scenarios[1]["level"] == 56
if __name__ == "__main__": main()
