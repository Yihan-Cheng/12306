sudo ps -ef | grep chrome | grep -v grep | awk '{print $2}' | xargs kill -9
sudo ps -ef | grep python3 | grep -v grep | awk '{print $2}' | xargs kill -9
python3 reptile.py
python3 generator.py