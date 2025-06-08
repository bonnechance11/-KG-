# coding=utf-8
from flask import Flask, jsonify, g,request,render_template,session,url_for,redirect
from flask_login import login_required,UserMixin
#from py2neo import Graph
from neo4j import GraphDatabase
#from flask_sqlalchemy import SQLAlchemy
#from flask_login import LoginManager
#from werkzeug.security import generate_password_hash, check_password_hash
import pyodbc

#连接neo4j和sqlserver
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "030331")) #认证连接数据库
conn = pyodbc.connect('DRIVER={SQL Server};SERVER=LAPTOP-3TQQRDSO;DATABASE=us;UID=sa;PWD=123456')


#查询数据库用户
def query_user(username):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM [user] WHERE username = ?", (username,))
    user = cursor.fetchone()
    cursor.close()
    if user:
        # 去掉用户名和密码的前后空格
        user = (user[0].strip(), user[1].strip())
    return user
    return user

# 插入新用户数据
def insert_user(username, password):
    cursor = conn.cursor()
    cursor.execute("INSERT INTO [user] (username, password) VALUES (?, ?)", (username, password))
    conn.commit()
    cursor.close()
    
app = Flask(__name__) #flask框架必备
app.secret_key = 'secret'


#登录界面
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = query_user(username)  # 查询用户信息
        if user and user[1] == password:  # 验证用户名和密码
            session['username'] = username  # 将用户名存储在 session 中# 将用户名存储在session中
            return redirect(url_for('get_input',username=username))  # 登录成功后直接跳转到输入页面
        else:
            return render_template('login.html', error=True)
    else:
         return render_template('login.html', error=False)

# 注册界面
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        insert_user(username, password)  # 将新用户插入数据库
        return redirect(url_for('login'))  # 注册成功后重定向到登录页面
    else:
        return render_template('register.html')  # 显示注册页面的模板
    
#输入界面    
@app.route('/input', methods=['GET', 'POST'])
def get_input():
    if request.method == 'POST':
        input_value = request.form['input']  # 获取用户输入
        return redirect(url_for('index', input=input_value,username=request.args.get('username')))  # 用户输入后跳转到主页
    else:
        return render_template('input.html')  # 显示输入页面的模板
def buildNodes(nodeRecord): #构建web显示节点
    data = {"id": nodeRecord._id, 
            "label": list(nodeRecord._labels)[0],
            "name": nodeRecord.get("name", "Unknown"),
             "explanation":nodeRecord.get("explanation","Unknown"),
             "about":nodeRecord.get("about","Unknown")
             } #将集合元素变为list，然后取出值
    data.update(dict(nodeRecord._properties))
    return {"data": data}

def buildEdges(relationRecord): #构建web显示边
    data = {"source": relationRecord.start_node._id,
            "target":relationRecord.end_node._id,
            "relationship": relationRecord.type}

    return {"data": data}

@app.route('/')#建立路由，指向网页
def index():
    username = request.args.get('username')
    global input1
    input1 = request.args.get('input')
    with driver.session() as session:
        paths1='MATCH (n:user{name:"'+input1+'"})-[:learn]->(c:course) RETURN c.prerequisites LIMIT 25'
        p1='MATCH (n:user{name:"'+input1+'"})-[r1:learn]->(c)-[r2:belongs]->(k:concept) RETURN DISTINCT c.name LIMIT 5'
        path2='MATCH (n:course{name:"'
        #path3='"})<-[r1:learn]-(u:user)-[r2:learn]->(rec:course) RETURN rec.name AS recommendation,count(*) as useralsolearn ORDER BY useralsolearn LIMIT 2'
        results1=session.run(paths1).values()
        
     #基于协同过滤和cypher查询的推荐
        r1=session.run(p1).values()
        path3 = f'''
        MATCH (user1:user {{name: "{input1}"}})-[:learn]->(common_course:course)<-[:learn]-(user2:user)
        WHERE user1.name <> user2.name
        WITH common_course,user1
        MATCH (common_course)<-[:learn]-(other_user:user)-[:learn]->(recommended_course:course)
        WHERE other_user.name <> "{input1}" AND NOT (user1)-[:learn]->(recommended_course)
        RETURN DISTINCT common_course.name AS cm,
        recommended_course.name AS rm,
        recommended_course.Top1 AS Top1,
        recommended_course.Top2 AS Top2,
        recommended_course.Top3 AS Top3
        LIMIT 2
       '''
        results2=session.run(path3).values()
        #基于用户偏好的协同过滤
        path4 = f"""
        WITH "{input1}" AS inputUserName
        MATCH (u:user {{name: inputUserName}})-[:learn]->(c:course)-[:belongs]->(concept)
        WITH concept, u, c, COUNT(DISTINCT c) AS concept_weight  // 使用 DISTINCT 避免重复计数
        ORDER BY concept_weight DESC
        MATCH (concept)<-[:belongs]-(recommended_course:course)
        WHERE NOT (u)-[:learn]->(recommended_course)
        WITH recommended_course, concept_weight, u
        MATCH (u)-[:learn]->(learned_course:course)
        WITH recommended_course, concept_weight, learned_course, u
        WHERE ANY (char IN RANGE(0, 5) 
           WHERE substring(recommended_course.name, char, 1) <> substring(learned_course.name, char, 1))
        RETURN recommended_course.name AS course_name, recommended_course.Top1, recommended_course.Top2, recommended_course.Top3, SUM(concept_weight) AS weight
        ORDER BY weight DESC
        LIMIT 2
        """
        r3=session.run(path4).values()
        #用户概念相似度的协同过滤
        path5 =' MATCH (u1:user {name: \"' + input1 + '\"})-[:learn]->(c1:course)'+\
        ' WITH u1,COLLECT(id(c1)) AS u1courses'+\
        ' MATCH (u1)-[:study]->(f1:concept)'+\
        ' WITH u1, u1courses, COLLECT(f1.name) AS u1fields'+\
        ' MATCH (u2:user)-[:learn]->(c2:course)'+\
        ' WHERE u2.name <> "'+input1+'"'+\
        ' WITH u1, u1courses, u1fields, u2, COLLECT(id(c2)) AS u2courses'+\
        ' WHERE SIZE(u2courses) >= 5'+\
        ' MATCH (u2)-[:study]->(f2:concept)'+\
        ' WITH u1, u1courses, u1fields, u2, u2courses, COLLECT(f2.name) AS u2fields'+\
        ' WITH u1, u1courses, u1fields, u2, u2courses, FILTER(f IN u2fields WHERE f IN u1fields) AS commonFields'+\
        ' WITH u1, u1courses, u1fields, u2, u2courses, commonFields, algo.similarity.jaccard(u1courses, u2courses) AS similarity'+\
        ' ORDER BY similarity DESC LIMIT 3'+\
        ' MATCH (u2)-[:learn]->(c:course)'+\
        ' WHERE NOT id(c) IN u1courses'+\
        ' WITH c, commonFields'+\
        ' RETURN commonFields, c.name AS course, c.Top1,c.Top2,c.Top3,COUNT(*) AS count'+\
        ' ORDER BY count DESC'+\
        ' LIMIT 2'


        r4 = session.run(path5).values()
        
    return render_template('index.html',username=username,input=input1,results1=results1,results2=results2,r3=r3,r4=r4)

@app.route('/graph')#两个路由指向同一个网页，返回图的节点和边的结构体
def get_graph():
    with driver.session() as session:  
        path='MATCH (n:user{name:"'+input1+'"})-[r1:learn]->(c)-[r2:belongs]->(k:concept) RETURN DISTINCT n,c,k,r1,r2 SKIP 0 LIMIT 50' 
        results=session.run(path).values()
        nodeList=[]
        edgeList=[]
        for result in results:
            nodeList.append(result[0])
            nodeList.append(result[1])
            nodeList.append(result[2])
            nodeList=list(set(nodeList))
            edgeList.append(result[4])
        nodes = list(map(buildNodes, nodeList))
        edges= list(map(buildEdges,edgeList))
    return jsonify(elements = {"nodes": nodes, "edges": edges})

if __name__ == '__main__':
    app.run(debug = False) #flask框架
    
  
    
    
    
    
    
    