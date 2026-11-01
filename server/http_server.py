import json
import os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, quote
from pydantic import ValidationError

from engine.workflow import TaskNotFound, WorkflowConflict


class APIHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器"""

    # 由工厂函数设置
    service = None
    web_dir = None

    def do_GET(self):
        path = urlparse(self.path).path

        try:
            if path == '/api/skills':
                self._json_response(self.service.get_skills_summary())
            elif path == '/api/state':
                self._json_response(self.service.get_state())
            elif path == '/api/tasks':
                self._json_response(self.service.list_tasks())
            elif path.startswith('/api/tasks/'):
                self._json_response(self.service.get_task(path.rsplit('/', 1)[-1]))
            elif path == '/api/config':
                self._json_response({'ws_port': self.service._config.server.ws_port})
            elif path == '/api/plans':
                self._json_response(self.service.list_saved_plans())
            elif path == '/api/plan-variables':
                self._json_response(self.service.get_plan_variables())
            elif path == '/api/device-params':
                self._json_response(self.service.get_device_params())
            elif path.startswith('/api/report/'):
                report_id = path.split('/')[-1]
                result = self.service.get_report_content(report_id)
                if result:
                    self._json_response(result)
                else:
                    self._json_response({'error': '报告不存在'}, 404)
            else:
                self._serve_static(path)
        except TaskNotFound as e:
            self._json_response({'error': str(e)}, 404)
        except Exception as e:
            self._json_response({'error': str(e)}, 500)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b''
        path = urlparse(self.path).path

        try:
            if path == '/api/upload-knowledge':
                data = json.loads(body)
                msg = self.service.upload_knowledge(data['content'])
                self._json_response({'success': True, 'message': msg})

            elif path == '/api/remove-knowledge':
                data = json.loads(body)
                self.service.remove_knowledge(data['index'])
                self._json_response({'success': True})

            elif path == '/api/generate-plan':
                data = json.loads(body) if body else {}
                instruction = data.get('instruction', '')
                self.service.generate_plan(instruction)
                self._json_response({'success': True, 'message': '正在生成测试计划...'})

            elif path == '/api/update-plan':
                data = json.loads(body)
                task = self.service.update_plan(data['plan'], data.get('revision'), data.get('task_id'))
                self._json_response({'success': True, 'task': task})

            elif path == '/api/review-plan':
                data = json.loads(body)
                task = self.service.review_plan(data['task_id'], data['revision'],
                                                data['approved'], data.get('comment', ''))
                self._json_response({'success': True, 'task': task})

            elif path == '/api/load-task':
                data = json.loads(body)
                self._json_response({'success': True, 'task': self.service.load_task(data['task_id'])})

            elif path == '/api/retry-report':
                data = json.loads(body)
                self.service.retry_report(data['task_id'])
                self._json_response({'success': True}, 202)

            elif path == '/api/resume-diagnosis':
                data = json.loads(body)
                self.service.resume_diagnosis(data['task_id'])
                self._json_response({'success': True}, 202)

            elif path == '/api/save-plan':
                data = json.loads(body)
                plan_id = self.service.save_plan(
                    data['plan'],
                    name=data.get('name'),
                    plan_id=data.get('plan_id'),
                )
                self._json_response({'success': True, 'plan_id': plan_id})

            elif path == '/api/load-plan':
                data = json.loads(body)
                plan = self.service.load_saved_plan(data['plan_id'])
                self._json_response({'success': True, 'plan': plan, 'task': self.service.get_state()})

            elif path == '/api/delete-plan':
                data = json.loads(body)
                self.service.delete_saved_plan(data['plan_id'])
                self._json_response({'success': True})

            elif path == '/api/start-test':
                data = json.loads(body) if body else {}
                variables = data.get('variables')
                self.service.start_test(variables=variables, task_id=data.get('task_id'),
                                        revision=data.get('revision'))
                self._json_response({'success': True, 'message': '测试已开始'})

            elif path == '/api/stop-test':
                self.service.stop_test()
                self._json_response({'success': True})

            elif path == '/api/pause-test':
                self.service.pause_test()
                self._json_response({'success': True})

            elif path == '/api/resume-test':
                self.service.resume_test()
                self._json_response({'success': True})

            elif path == '/api/generate-report':
                report_id, report = self.service.generate_report()
                self._json_response({
                    'success': True,
                    'report_id': report_id,
                    'report': report,
                })

            elif path == '/api/reset':
                self.service.reset()
                self._json_response({'success': True})

            elif path == '/api/export-plan':
                data = json.loads(body)
                filename, zip_bytes = self.service.export_plan(data['plan'])
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition',
                                 "attachment; filename*=UTF-8''" + quote(filename))
                self.send_header('Content-Length', len(zip_bytes))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(zip_bytes)
                return

            elif path == '/api/import-plan':
                plan = self.service.import_plan(body)
                self._json_response({'success': True, 'plan': plan, 'task': self.service.get_state()})

            else:
                self._json_response({'error': 'Not Found'}, 404)

        except ValidationError as e:
            errors = e.errors(include_input=False, include_url=False, include_context=False)
            self._json_response({'success': False, 'error': '计划结构校验失败', 'details': errors}, 400)
        except WorkflowConflict as e:
            self._json_response({'success': False, 'error': str(e)}, 409)
        except TaskNotFound as e:
            self._json_response({'success': False, 'error': str(e)}, 404)
        except (ValueError, KeyError, TypeError) as e:
            self._json_response({'success': False, 'error': str(e)}, 400)
        except Exception as e:
            self._json_response({'success': False, 'error': str(e)}, 500)

    def do_OPTIONS(self):
        """CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def _serve_static(self, path):
        if path == '/' or path == '':
            path = '/index.html'

        file_path = os.path.join(self.web_dir, path.lstrip('/'))

        # 防止路径穿越
        file_path = os.path.realpath(file_path)
        if not file_path.startswith(os.path.realpath(self.web_dir)):
            self.send_error(403)
            return

        if not os.path.isfile(file_path):
            self.send_error(404)
            return

        ext = os.path.splitext(file_path)[1]
        content_types = {
            '.html': 'text/html; charset=utf-8',
            '.css': 'text/css; charset=utf-8',
            '.js': 'application/javascript; charset=utf-8',
            '.json': 'application/json; charset=utf-8',
            '.png': 'image/png',
            '.svg': 'image/svg+xml',
        }
        content_type = content_types.get(ext, 'application/octet-stream')

        with open(file_path, 'rb') as f:
            content = f.read()

        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(content))
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        pass


def create_handler(service, web_dir):
    """工厂函数：创建绑定了 service 引用的 Handler 子类"""
    class Handler(APIHandler):
        pass
    Handler.service = service
    Handler.web_dir = web_dir
    return Handler


def start_http_server(service, host='0.0.0.0', port=8080, web_dir='web'):
    """启动 HTTP 服务"""
    handler = create_handler(service, web_dir)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"[HTTP] 服务启动: http://{host}:{port}")
    server.serve_forever()
