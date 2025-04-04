# Run in docker specific notes

## get submodules

```
git submodule update --init --recursive
```

## run the script

```bash
docker run -it --rm admin_py python client.py --env=devbrown
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
