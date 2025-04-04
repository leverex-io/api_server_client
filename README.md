# How to start the software

## get submodules

```
git submodule update --init --recursive
```

## run in venv linux/mac

```

python -m venv apiclient
source apiclient/bin/activate
pip install -r requirements.txt
python client.py --env=devbrown
```

## run in venv windows

```
python -m venv apiclient
apiclient\Scripts\activate
pip install -r requirements.txt
python client.py --env=devbrown
```

## run the script in docker

```bash
docker build -t admin_py .
docker run -it --rm admin_py python client.py --env=devbrown
```
