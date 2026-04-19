from Web.app import app
with app.test_client() as client:
    resp = client.get('/terminplan')
    print(resp.status_code)
    # print(resp.data.decode('utf-8')[:200])
