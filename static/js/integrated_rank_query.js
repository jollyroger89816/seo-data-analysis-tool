// 整合的排名查询功能
let currentExtractSessionId = null;
let currentQuerySessionId = null;
let progressInterval = null;

// 显示关键词提取结果
function displayExtractResults() {
    if (!currentExtractSessionId) {
        return;
    }
    
    fetch(`/get_extract_results/${currentExtractSessionId}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                alert('获取结果失败: ' + data.error);
                return;
            }
            
            // 显示结果统计
            const results = data.results || [];
            const successCount = results.filter(r => r.status === '成功').length;
            const titleCount = results.filter(r => r.status === '使用标题').length;
            const failedCount = results.filter(r => r.status === '失败').length;
            
            const statsHtml = `
                <div class="alert alert-success">
                    <h6><i class="fas fa-check-circle me-2"></i>关键词提取完成</h6>
                    <div class="row">
                        <div class="col-md-3">
                            <strong>总计:</strong> ${results.length} 个
                        </div>
                        <div class="col-md-3">
                            <strong>成功:</strong> <span class="text-success">${successCount}</span> 个
                        </div>
                        <div class="col-md-3">
                            <strong>使用标题:</strong> <span class="text-warning">${titleCount}</span> 个
                        </div>
                        <div class="col-md-3">
                            <strong>失败:</strong> <span class="text-danger">${failedCount}</span> 个
                        </div>
                    </div>
                </div>
            `;
            
            // 添加统计信息
            const statsDiv = document.getElementById('extract-stats');
            if (statsDiv) {
                statsDiv.innerHTML = statsHtml;
            }
            
            // 显示关键词结果表格
            displayKeywordsTable(results);
            
            // 显示结果区域和查询按钮
            document.getElementById('extract-results-section').style.display = 'block';
            document.getElementById('show-query-btn').style.display = 'inline-block';
            
            // 设置表格类型
            setTableType('关键词列表', 'bg-secondary');
        })
        .catch(error => {
            console.error('获取结果失败:', error);
            alert('获取结果失败: ' + error.message);
        });
}

// 显示关键词表格
function displayKeywordsTable(results) {
    const tbody = document.getElementById('unified-results-table');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    // 显示关键词表头
    showTableHeader('keywords');
    
    results.forEach(result => {
        const row = document.createElement('tr');
        
        let statusClass = getStatusClass(result.status);
        let statusText = result.status || '未知';
        
        row.innerHTML = `
            <td>${result.index}</td>
            <td>${result.id || '-'}</td>
            <td><a href="${result.url}" target="_blank" class="text-decoration-none">${result.url.substring(0, 40)}...</a></td>
            <td>${result.keywords || '-'}</td>
            <td>${result.title || '-'}</td>
            <td>${result.domain}</td>
            <td>${result.final_keyword || '-'}</td>
            <td><span class="${statusClass}">${statusText}</span></td>
            <td>${result.previous_uv?.toLocaleString() || 'N/A'}</td>
            <td>${result.decline_amount?.toLocaleString() || 'N/A'}</td>
        `;
        tbody.appendChild(row);
    });
}

// 显示排名查询结果表格
function displayRankingTable(results) {
    const tbody = document.getElementById('unified-results-table');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    // 显示排名结果表头
    showTableHeader('results');
    
    results.forEach(result => {
        const row = document.createElement('tr');
        
        let trafficInfo = '';
        if (result.previous_uv && result.decline_amount) {
            trafficInfo = `去年UV: ${result.previous_uv.toLocaleString()}<br>下降: ${result.decline_amount.toLocaleString()}`;
        } else {
            trafficInfo = '手动查询无流量数据';
        }
        
        row.innerHTML = `
            <td>${result.index}</td>
            <td><a href="${result.url}" target="_blank" class="text-decoration-none">${result.url.substring(0, 40)}...</a></td>
            <td>${result.final_keyword || result.keywords || '-'}</td>
            <td>${result.domain}</td>
            <td><strong>${result.rank}</strong></td>
            <td>${result.site_count || 0}</td>
            <td><small>${trafficInfo}</small></td>
            <td>${result.error ? '<span class="text-danger">失败</span>' : '<span class="text-success">成功</span>'}</td>
        `;
        tbody.appendChild(row);
    });
    
    // 更新表格类型标识
    setTableType('排名查询结果', 'bg-success');
    
    // 显示导出结果按钮
    const exportBtn = document.getElementById('export-results-btn');
    if (exportBtn) {
        exportBtn.style.display = 'inline-block';
    }
}

// 显示整合的排名查询表单
function showIntegratedRankQuery() {
    document.getElementById('rank-query-integrated').style.display = 'block';
    document.getElementById('show-query-btn').style.display = 'none';
}

// 开始整合的排名查询
function startIntegratedRankQuery() {
    const apiKey = document.getElementById('api-key-integrated').value.trim();
    
    if (!apiKey) {
        alert('请输入站长之家API Key');
        return;
    }
    
    if (!currentExtractSessionId) {
        alert('请先提取关键词');
        return;
    }
    
    fetch('/query_by_keywords', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            api_key: apiKey,
            session_id: currentExtractSessionId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            alert('错误: ' + data.error);
        } else {
            currentQuerySessionId = data.session_id;
            document.getElementById('query-progress-integrated').style.display = 'block';
            document.getElementById('cancel-query-integrated-btn').style.display = 'inline-block';
            document.getElementById('rank-query-integrated').style.display = 'none';
            
            // 开始监控查询进度
            monitorIntegratedQueryProgress();
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('启动排名查询失败');
    });
}

// 监控整合的排名查询进度
function monitorIntegratedQueryProgress() {
    if (!currentQuerySessionId) return;
    
    fetch(`/api/query_progress/${currentQuerySessionId}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                document.getElementById('query-status-integrated').textContent = '错误: ' + data.error;
                return;
            }
            
            const progressBar = document.getElementById('query-progress-bar-integrated');
            const progressText = document.getElementById('query-progress-text-integrated');
            const statusText = document.getElementById('query-status-integrated');
            const currentUrlText = document.getElementById('query-current-url-integrated');
            
            progressBar.style.width = data.progress_percent + '%';
            progressText.textContent = data.progress_percent + '%';
            statusText.textContent = `${data.status} (${data.completed}/${data.total})`;
            currentUrlText.textContent = data.current_url;
            
            if (data.status === 'finished') {
                // 查询完成，获取结果
                loadIntegratedQueryResults();
                document.getElementById('cancel-query-integrated-btn').style.display = 'none';
                document.getElementById('query-progress-integrated').style.display = 'none';
            } else if (data.status === 'cancelled') {
                statusText.textContent = '已取消';
                document.getElementById('cancel-query-integrated-btn').style.display = 'none';
                document.getElementById('query-progress-integrated').style.display = 'none';
                document.getElementById('show-query-btn').style.display = 'inline-block';
            } else if (data.status === 'error') {
                statusText.textContent = '错误';
                document.getElementById('cancel-query-integrated-btn').style.display = 'none';
                document.getElementById('query-progress-integrated').style.display = 'none';
                document.getElementById('show-query-btn').style.display = 'inline-block';
            } else {
                // 继续监控
                setTimeout(monitorIntegratedQueryProgress, 1000);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            setTimeout(monitorIntegratedQueryProgress, 2000);
        });
}

// 加载整合的查询结果
function loadIntegratedQueryResults() {
    if (!currentQuerySessionId) return;
    
    fetch(`/get_query_results/${currentQuerySessionId}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                alert('获取查询结果失败: ' + data.error);
                return;
            }
            
            if (data.status === 'finished') {
                displayRankingTable(data.results);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('获取查询结果失败');
        });
}

// 辅助函数
function getStatusClass(status) {
    switch (status) {
        case '成功':
            return 'text-success';
        case '使用标题':
            return 'text-warning';
        case '无关键词':
            return 'text-info';
        case '失败':
            return 'text-danger';
        default:
            return 'text-secondary';
    }
}

function showTableHeader(type) {
    const keywordsHeader = document.getElementById('table-header-keywords');
    const resultsHeader = document.getElementById('table-header-results');
    
    if (type === 'keywords') {
        keywordsHeader.style.display = '';
        resultsHeader.style.display = 'none';
    } else {
        keywordsHeader.style.display = 'none';
        resultsHeader.style.display = '';
    }
}

function setTableType(text, className) {
    const badge = document.getElementById('table-type-badge');
    if (badge) {
        badge.textContent = text;
        badge.className = `badge ${className}`;
    }
}

// 取消查询
function cancelQuery() {
    if (!currentQuerySessionId) return;
    
    fetch(`/api/cancel_query/${currentQuerySessionId}`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('query-status-integrated').textContent = '已取消';
            document.getElementById('cancel-query-integrated-btn').style.display = 'none';
        }
    })
    .catch(error => {
        console.error('Error:', error);
    });
} 