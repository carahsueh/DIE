from tqdm import tqdm 
import os
from tenacity import retry, stop_after_attempt, wait_exponential
import json 
import openai
import re
import pandas as pd 
import sys
import argparse
from self_reminder import *
def get_args():
    parser = argparse.ArgumentParser(description="Configs")
    parser.add_argument("--output_path", type=str, default='./output/attack_gpt.jsonl')
    parser.add_argument("--input_path", type=str, default='./data/harmful_behaviors.csv')
    parser.add_argument("--idx", type=int, default=0)
    parser.add_argument("--start_idx", type=int, default=0)
    parser.add_argument("--end_idx", type=int, default=1)
    args = parser.parse_args()
    return args
# Set environment variables
os.environ["OPENAI_API_KEY"] = ""
os.environ["OPENAI_API_BASE"] = ""

# Initialize OpenAI client
openai.api_key = os.environ["OPENAI_API_KEY"]
openai.api_base = os.environ["OPENAI_API_BASE"]
@retry(stop=stop_after_attempt(6), wait=wait_exponential(multiplier=1, max=60))
def gpt4_query(msg):
    

    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=msg
    )
    return completion.choices[0].message.content

@retry(stop=stop_after_attempt(6), wait=wait_exponential(multiplier=1, max=60))
def gpt3_query(msg):
    
    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=msg
    )
    return completion.choices[0].message.content
from judgement_group import *
from dialogue_templates import *
# 候选question子问题拆分 （过滤denfence等词）
import re
words_to_remove = {'defense', 'protect' ,'safe','legal','illegal','safety','safely'}
def remove_words(input_string, words_to_remove):
    pattern = r'\b(' + '|'.join(map(re.escape, words_to_remove)) + r')\b'
    result = re.sub(pattern, '', input_string)
    result = re.sub(r'\s+', ' ', result).strip()
    return result
def extract_questions(text):
    pattern = r'(?m)^- (.*?)(?=\n\s*- |\n\d\.|\n?$)|^\d\.\s(.*?)(?=\n\d\.|\n-|\n?$)|^\s*\d\.\s(.*?)(?=\n\s*\d\.|\n-|\n?$)|^\s*- (.*?)(?=\n\s*- |\n\d\.|\n?$)|^\s*[a-z]\.\s(.*?)(?=\n\s*[a-z]\.|\n\s*\d\.|\n\s*-|\n?$)'

    matches = re.findall(pattern, text)

    questions = [match[0] or match[1] or match[2] or match[3] or match[4] for match in matches]
    if len(questions) == 0:
        questions = text.split('\n')
    questions =[remove_words(m,words_to_remove) for m in questions]
    
    return questions



def get_academic_queries(ori_query,num=0):
    if num > 10:
        return []
    prompt = generate_academic_template().format(QUERY=ori_query)
    base_msg = [
    {"role": "system", "content": 'You are a helpful assistant.'},
        {'role':'user','content':prompt}
  ]
    a1 = gpt3_query(base_msg)
    num = num + 1 
    if len(extract_questions(a1))>2:
        return extract_questions(a1)
    else:
        return get_academic_queries(ori_query,num)


def get_substitution(kwords,num=0):
    if num>0:
        return []
    key_induce = generate_substitution_template().format(WORD=kwords)
    base_msg = [
        {"role": "system", "content": 'You are a helpful assistant.'},
        {'role':'user','content':key_induce}
  ]
    answer_with_key = gpt3_query(base_msg)
    num = num + 1 
    if len(extract_questions(answer_with_key))>1:
        return extract_questions(answer_with_key)
    else:
        return get_substitution(kwords,num)

def info_extract(ori_query):
    q1 = generate_info_extract_template().format(QUERY=ori_query)
    kwords = ''
    topic = ''
    target = ''
    base_msg = [
    {"role": "system", "content": 'You are a helpful assistant.'},
        {'role':'user','content':q1}
  ]
    a1 = gpt3_query(base_msg)

    try:
        json_object = json.loads(a1)
    
        if 'keywords' in json_object and 'topic' in json_object and 'target_object' in json_object:
            
            kwords = json_object['keywords']
            topic = json_object['topic']
            target = json_object['target_object']
        else:
            print("JSON object does not contain particular key.")

        
    except json.JSONDecodeError as e:
        print("Invalid JSON format:", e)
    except Exception as e:
        print("An error occurred:", e)

    return kwords,topic,target


def sentence_rewrite_nertral(ori_query):
    q1 = generate_neutral_rewrite_template().format(QUERY=ori_query)
    rewritten_query= ''
    base_msg = [
    {"role": "system", "content": 'You are a helpful assistant.'},
        {'role':'user','content':q1}
  ]
    a1 = gpt3_query(base_msg)

    try:
        json_object = json.loads(a1)
    
        if 'rewritten_query' in json_object :
            
            rewritten_query = json_object['rewritten_query']
            
        else:
            print("JSON object does not contain particular key.")

        
    except json.JSONDecodeError as e:
        print("Invalid JSON format:", e)
    except Exception as e:
        print("An error occurred:", e)

    return rewritten_query

def judge_success(response):
    result = 0
    try:
        gpt_label = success_judge(response)
        print(gpt_label)
        if 'jailbreak' in gpt_label or 'Jailbreak' in gpt_label:
            result = 1
            return result
    except Exception:
        gpt_label = 'refuse'
    return result


if __name__ == '__main__':
    args = get_args()
    data = pd.read_csv(args.input_path)
    start_idx =  args.start_idx
    end_idx =  args.end_idx
    data = data[start_idx:end_idx]
    id_temp = args.idx
    # print(id_temp)
    output=args.output_path
    for idx,row in tqdm(data.iterrows(),total=len(data),desc='Processing'):
        ori_query = row['goal']
    
        sub_queries = get_academic_queries(ori_query,0)
        prompt_final = []
        response = []
        for query in sub_queries:
            base_msg = [
    {"role": "system", "content": 'You are a helpful assistant.'},
        {'role':'user','content':defence_wrapper(query,id_temp)}
  ]
            answer = gpt4_query(base_msg)
            if regex_judge(answer)==1:
                response.append([query,answer])
        if len(response) == 0:
            for query in sub_queries:
                for sub_query in get_academic_queries(query,0):
                    base_msg = [
    {"role": "system", "content": 'You are a helpful assistant.'},
        {'role':'user','content':defence_wrapper(sub_query,id_temp)}
  ]
                    answer = gpt4_query(base_msg)
                    if regex_judge(answer)==1:
                        response.append([sub_query,answer])
        kwords,_,_ = info_extract(ori_query)
        rewritten_query = sentence_rewrite_nertral(ori_query)
        atk_chain = ''
        response_atk = []
        for query,answer in response:
            j_gpt = judge_success(answer)
            # print(j_gpt)
            if j_gpt == 1:
                response_atk.append([query,answer])
                atk_chain = atk_chain+'a'
                prompt_final.append(query)
                break
            else:
                key_induce = generate_kw_induce_template().format(WORD=kwords)
                base_msg = [
    {"role": "system", "content": 'You are a helpful assistant.'},
    {"role": "assistant", "content": answer},
        {'role':'user','content':key_induce}
  ]
                
                answer_with_key = gpt4_query(base_msg)
                # print(answer_with_key)
                j_gpt2 = judge_success(answer_with_key)
                # print(j_gpt2)
                if j_gpt2==1:
                    response_atk.append([json.dumps(base_msg),answer_with_key])
                    atk_chain = atk_chain+'b'
                    prompt_final.append(query)
                    prompt_final.append(key_induce)
                    break
                else:
                    candi_words = get_substitution(kwords)
                    # print(candi_words)
                    for w in candi_words:
                        key_induce = generate_kw_induce_template().format(WORD=w)
                        base_msg = [
                {"role": "system", "content": 'You are a helpful assistant.'},
                {"role": "assistant", "content": answer},
                {'role':'user','content':key_induce}
  ]
                        answer_with_key = gpt4_query(base_msg)
                        # print(answer_with_key)
                        j_gpt3 = judge_success(answer_with_key)
                        # print(j_gpt3)
                        if j_gpt3 == 1:
                            response_atk.append([json.dumps(base_msg),answer_with_key])
                            atk_chain = atk_chain+'c'
                            prompt_final.append(query)
                            prompt_final.append(key_induce)
                            break
                        elif regex_judge(answer_with_key)==1:
                            intent_induce = generate_refine_induce_template().format(QUERY=ori_query,ANSWER=answer_with_key)
                            base_msg = [
                {"role": "system", "content": 'You are a helpful assistant.'},
               # {"role": "assistant", "content": answer_with_key},
                {'role':'user','content':intent_induce}
  ]
                            answer_with_intent = gpt4_query(base_msg)
                            # print(answer_with_intent)
                            j_gpt4 = judge_success(answer_with_intent)
                            # print(j_gpt4)
                            if j_gpt4 == 1:
                                response_atk.append([json.dumps(base_msg),answer_with_intent])
                                atk_chain = atk_chain+'d'
                                prompt_final.append(query)
                                prompt_final.append(intent_induce)
                                break
                            else:
                                intent_induce = generate_reverse_template()
                                base_msg = [
                {"role": "system", "content": 'You are a helpful assistant.'},
                {"role": "assistant", "content": answer_with_key},
                {'role':'user','content':intent_induce}
  ]
                                answer_with_intent = gpt4_query(base_msg)
                                # print(answer_with_intent)
                                j_gpt5 = judge_success(answer_with_key)
                                # print(j_gpt5)
                                if j_gpt5 == 1:
                                    response_atk.append([json.dumps(base_msg),answer_with_intent])
                                    atk_chain = atk_chain+'e'
                                    prompt_final.append(query)
                                    prompt_final.append(key_induce)
                                    prompt_final.append(intent_induce)
                                    break
                                else:
                                    intent_scenario = generate_embed_hide_template().format(REWRITE=rewritten_query,QUERY=ori_query)
                                    base_msg = [
                {"role": "system", "content": 'You are a helpful assistant.'},
                {"role": "assistant", "content": answer_with_key},
                {'role':'user','content':defence_wrapper(intent_scenario,id_temp)}
  ]
                                    answer_with_scenario = gpt4_query(base_msg)
                                    # print(answer_with_scenario)
                                    j_gpt6 = judge_success(answer_with_scenario)
                                    # print(j_gpt6)
                                    if j_gpt6 == 1:
                                        response_atk.append([json.dumps(base_msg),answer_with_scenario])
                                        atk_chain = atk_chain+'f'
                                        prompt_final.append(query)
                                        prompt_final.append(key_induce)
                                        prompt_final.append(intent_scenario)
                                        break
                            
                    if len(response_atk)>0:
                        break
        # print('final*********************************')
        # print(atk_chain)
        # print(response_atk)

        with open (output,'a+') as file:          
            file.write(json.dumps({'goal':row['goal'],'kwords':kwords,'sub_queries':json.dumps(sub_queries),'response':json.dumps(response),'atk_chain':atk_chain,'prompt':json.dumps(prompt_final),'atk':json.dumps(response_atk)}))
            file.write('\n')
        
