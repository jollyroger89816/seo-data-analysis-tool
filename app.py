from config import ServiceConfig

@app.route('/api/get_service_config')
def get_service_config():
    """获取服务配置"""
    try:
        return jsonify({
            'success': True,
            'main_port': ServiceConfig.MAIN_SERVICE_PORT,
            'rank_query_port': ServiceConfig.RANK_QUERY_PORT,
            'dev_mode': ServiceConfig.DEV_MODE,
            'api_version': ServiceConfig.API_VERSION
        })
    except Exception as e:
        logging.error(f"获取服务配置失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500 