// ==UserScript==
// @name         滴答清单助手
// @namespace    http://tampermonkey.net/
// @version      0.1
// @description  滴答清单数据统计助手，支持工作量统计、标签统计等功能
// @author       Your Name
// @match        https://dida365.com/*
// @match        https://api.dida365.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_addStyle
// ==/UserScript==

(function() {
    'use strict';

    // 添加样式
    GM_addStyle(`
        .dida-helper-panel {
            position: fixed;
            top: 60px;
            right: 20px;
            background: white;
            border: 1px solid #ccc;
            border-radius: 8px;
            padding: 15px;
            z-index: 9999;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            width: 300px;
        }
        .dida-helper-panel h3 {
            margin: 0 0 10px 0;
            padding-bottom: 10px;
            border-bottom: 1px solid #eee;
        }
        .dida-helper-btn {
            background: #2ecc71;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 4px;
            cursor: pointer;
            margin: 5px;
            font-size: 14px;
        }
        .dida-helper-btn:hover {
            background: #27ae60;
        }
        .dida-helper-result {
            margin-top: 15px;
            max-height: 400px;
            overflow-y: auto;
            font-size: 14px;
        }
        .tag-stat {
            display: flex;
            justify-content: space-between;
            margin: 5px 0;
            padding: 5px;
            background: #f9f9f9;
            border-radius: 4px;
        }
        .copy-btn {
            color: #1890ff;
            cursor: pointer;
            font-size: 14px;
            margin-left: 10px;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }
        .copy-btn:hover {
            color: #40a9ff;
        }
        .copy-btn::before {
            content: "📋";
            font-size: 16px;
        }
        .dida-helper-input {
            margin: 5px;
            padding: 5px;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-size: 14px;
        }
        .tag-select {
            width: 100%;
            margin: 10px 0;
            padding: 8px;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-size: 14px;
        }
        .trend-item {
            margin: 8px 0;
            padding: 8px;
            background: #f0f7ff;
            border-left: 3px solid #1890ff;
            border-radius: 4px;
        }
        .trend-month {
            font-weight: bold;
            color: #1890ff;
            margin-bottom: 5px;
        }
        .trend-hours {
            color: #666;
            font-size: 13px;
        }
        .trend-chart {
            margin-top: 20px;
            padding: 15px;
            background: #f9f9f9;
            border-radius: 4px;
        }
        .trend-chart canvas {
            width: 100%;
            height: 200px;
        }
        .chart-zoom-btn {
            margin-top: 10px;
            padding: 6px 12px;
            background: #1890ff;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        .chart-zoom-btn:hover {
            background: #40a9ff;
        }
        .chart-modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            z-index: 10000;
            justify-content: center;
            align-items: center;
        }
        .chart-modal.active {
            display: flex;
        }
        .chart-modal-content {
            background: white;
            border-radius: 8px;
            padding: 20px;
            max-width: 90%;
            max-height: 90%;
            position: relative;
        }
        .chart-modal-close {
            position: absolute;
            top: 10px;
            right: 10px;
            background: #f0f0f0;
            border: none;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            cursor: pointer;
            font-size: 18px;
            line-height: 1;
        }
        .chart-modal-close:hover {
            background: #e0e0e0;
        }
        .chart-modal canvas {
            width: 800px;
            height: 400px;
        }
    `);

    // 工具函数：获取北京时间，格式化为 YYYY-MM-DD HH:mm:ss
    function getBeiJingTime(dateTimeStr) {
        const date = new Date(dateTimeStr);
        const options = { timeZone: 'Asia/Shanghai' };
        const beijingDate = new Date(date.toLocaleString('en-US', options));

        const year = beijingDate.getFullYear();
        const month = String(beijingDate.getMonth() + 1).padStart(2, '0');
        const day = String(beijingDate.getDate()).padStart(2, '0');
        const hours = String(beijingDate.getHours()).padStart(2, '0');
        const minutes = String(beijingDate.getMinutes()).padStart(2, '0');
        const seconds = String(beijingDate.getSeconds()).padStart(2, '0');

        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    }

    // 工具函数：计算时间差（分钟）
    function getDuration(startTime, endTime) {
        const start = new Date(startTime);
        const end = new Date(endTime);
        return Math.floor((end - start) / (1000 * 60));
    }

    // 创建控制面板
    function createPanel() {
        const panel = document.createElement('div');
        panel.className = 'dida-helper-panel';
        panel.innerHTML = `
            <h3>滴答清单助手</h3>
            <div>
                <input type="date" id="startDate" class="dida-helper-input">
                <input type="date" id="endDate" class="dida-helper-input">
            </div>
            <div>
                <button class="dida-helper-btn" id="getStats">获取统计</button>
            </div>
            <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #eee;">
                <h4 style="margin: 0 0 10px 0; font-size: 14px;">标签趋势分析</h4>
                <select id="tagSelect" class="tag-select">
                    <option value="">请先获取统计以加载标签</option>
                </select>
                <button class="dida-helper-btn" id="getTrend" style="width: 100%; margin-top: 10px;">查看趋势</button>
            </div>
            <div class="dida-helper-result" id="resultArea"></div>
        `;
        document.body.appendChild(panel);

        // 设置默认日期，格式化为 YYYY-MM-DD HH:mm:ss
        const today = new Date();
        const todayFormatted = getBeiJingTime(today);
        document.getElementById('endDate').value = todayFormatted.split(' ')[0];

        const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
        const monthStartFormatted = getBeiJingTime(monthStart);
        document.getElementById('startDate').value = monthStartFormatted.split(' ')[0];

        // 添加事件监听
        document.getElementById('getStats').addEventListener('click', getStatistics);
        document.getElementById('getTrend').addEventListener('click', getTagTrend);
    }

    // 将时间范围分割成多个6个月的区间
    function splitTimeRange(startDate, endDate) {
        const start = new Date(startDate);
        const end = new Date(endDate);
        const ranges = [];
        let currentStart = new Date(start);

        while (currentStart < end) {
            const currentEnd = new Date(currentStart);
            currentEnd.setMonth(currentEnd.getMonth() + 6);
            currentEnd.setDate(currentEnd.getDate() - 1);

            if (currentEnd > end) {
                currentEnd.setTime(end.getTime());
            }

            const startStr = getBeiJingTime(currentStart).split(' ')[0] + ' 00:00:00';
            const endStr = getBeiJingTime(currentEnd).split(' ')[0] + ' 23:59:59';

            ranges.push({ start: startStr, end: endStr });

            currentStart = new Date(currentEnd);
            currentStart.setDate(currentStart.getDate() + 1);
            currentStart.setHours(0, 0, 0, 0);
        }

        return ranges;
    }

    // 查询接口数据（自动处理超过6个月的情况）
    async function fetchCompletedTasks(startDate, endDate) {
        const start = new Date(startDate);
        const end = new Date(endDate);
        const sixMonthsInMs = 6 * 30 * 24 * 60 * 60 * 1000;
        const timeDiff = end - start;

        if (timeDiff <= sixMonthsInMs) {
            const response = await fetch(`https://api.dida365.com/api/v2/project/all/completedInAll/?from=${startDate}&to=${endDate}&limit=1200`, {
                headers: {
                    'Accept': 'application/json'
                },
                credentials: 'include'
            });
            return await response.json();
        } else {
            const ranges = splitTimeRange(startDate, endDate);
            const allData = [];

            for (let i = 0; i < ranges.length; i++) {
                const range = ranges[i];
                const response = await fetch(`https://api.dida365.com/api/v2/project/all/completedInAll/?from=${range.start}&to=${range.end}&limit=1200`, {
                    headers: {
                        'Accept': 'application/json'
                    },
                    credentials: 'include'
                });
                const data = await response.json();
                if (data && data.length) {
                    allData.push(...data);
                }
            }

            return allData;
        }
    }

    // 获取统计数据
    async function getStatistics() {
        // 获取日期并添加时间部分
        const startDate = document.getElementById('startDate').value + ' 00:00:00';
        const endDate = document.getElementById('endDate').value + ' 23:59:59';
        const resultArea = document.getElementById('resultArea');

        resultArea.innerHTML = '正在获取数据...';

        try {
            const data = await fetchCompletedTasks(startDate, endDate);
            if (!data || !data.length) {
                resultArea.innerHTML = '未找到数据';
                return;
            }

            // 统计数据
            const tagStats = {};
            let totalDuration = 0;

            data.forEach(item => {
                if (!item.startDate || !item.dueDate) return;

                const duration = getDuration(item.startDate, item.dueDate);
                totalDuration += duration;

                (item.tags || []).forEach(tag => {
                    if (!tagStats[tag]) {
                        tagStats[tag] = { count: 0, duration: 0 };
                    }
                    tagStats[tag].count++;
                    tagStats[tag].duration += duration;
                });
            });

            // 生成报告
            let report = `
                <h4>统计报告 <span class="copy-btn" id="copyReport">复制</span></h4>
                <p>开始时间：${startDate} </p>
                <p>结束时间：${endDate} </p>
                <p>总任务数：${data.length}</p>
                <p>总工作时长：${(totalDuration / 60).toFixed(1)}小时</p>
                <h4>标签统计：</h4>
            `;

            const tagStatsArray = Object.entries(tagStats)
                .sort((a, b) => b[1].duration - a[1].duration);

            tagStatsArray.forEach(([tag, stats]) => {
                const percentage = totalDuration > 0 ? ((stats.duration / totalDuration) * 100).toFixed(1) : '0.0';
                report += `
                    <div class="tag-stat">
                        <span>${tag}</span>
                        <span>${stats.count}项 / ${(stats.duration / 60).toFixed(1)}小时 / ${percentage}%</span>
                    </div>
                `;
            });

            resultArea.innerHTML = report;

            // 更新标签选择器
            const tagSelect = document.getElementById('tagSelect');
            tagSelect.innerHTML = '<option value="">请选择标签</option>';
            tagStatsArray.forEach(([tag]) => {
                const option = document.createElement('option');
                option.value = tag;
                option.textContent = tag;
                tagSelect.appendChild(option);
            });

            // 保存数据供趋势分析使用
            window.didaHelperData = data;

            // 添加复制功能
            document.getElementById('copyReport').addEventListener('click', () => {
                let textReport = `统计报告\n`;
                textReport += `开始时间：${startDate}\n`;
                textReport += `结束时间：${endDate}\n`;
                textReport += `总任务数：${data.length}\n`;
                textReport += `总工作时长：${(totalDuration / 60).toFixed(1)}小时\n\n`;
                textReport += `标签统计：\n`;

                tagStatsArray.forEach(([tag, stats]) => {
                    const percentage = totalDuration > 0 ? ((stats.duration / totalDuration) * 100).toFixed(1) : '0.0';
                    textReport += `${tag}：${stats.count}项 / ${(stats.duration / 60).toFixed(1)}小时 / ${percentage}%\n`;
                });

                navigator.clipboard.writeText(textReport).then(() => {
                    const btn = document.getElementById('copyReport');
                    const originalText = btn.textContent;
                    btn.textContent = '已复制';
                    setTimeout(() => {
                        btn.textContent = originalText;
                    }, 2000);
                }).catch(err => {
                    alert('复制失败：' + err.message);
                });
            });

        } catch (error) {
            resultArea.innerHTML = `获取数据失败：${error.message}`;
        }
    }

    function showZoomedChart(months, monthlyStats, tagName) {
        let modal = document.getElementById('chartModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'chartModal';
            modal.className = 'chart-modal';
            modal.innerHTML = `
                <div class="chart-modal-content">
                    <button class="chart-modal-close" id="closeChartModal">×</button>
                    <h3 style="margin-top: 0;">${tagName} - 趋势图</h3>
                    <canvas id="zoomedTrendChart"></canvas>
                </div>
            `;
            document.body.appendChild(modal);

            document.getElementById('closeChartModal').addEventListener('click', () => {
                modal.classList.remove('active');
            });

            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    modal.classList.remove('active');
                }
            });
        }

        modal.classList.add('active');

        setTimeout(() => {
            drawTrendChart(months, monthlyStats, 'zoomedTrendChart', 800, 400);
        }, 100);
    }

    function drawTrendChart(months, monthlyStats, canvasId = 'trendChart', width = null, height = 200) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const finalWidth = width || canvas.offsetWidth;
        const finalHeight = height;
        canvas.width = finalWidth;
        canvas.height = finalHeight;

        const padding = finalHeight > 300
            ? { top: 30, right: 30, bottom: 50, left: 60 }
            : { top: 20, right: 20, bottom: 40, left: 50 };
        const chartWidth = finalWidth - padding.left - padding.right;
        const chartHeight = finalHeight - padding.top - padding.bottom;

        const maxHours = Math.max(...months.map(m => monthlyStats[m] / 60), 1);
        const barWidth = chartWidth / months.length * 0.7;
        const barSpacing = chartWidth / months.length;
        const fontSize = finalHeight > 300 ? 14 : 10;
        const labelFontSize = finalHeight > 300 ? 12 : 10;

        ctx.clearRect(0, 0, finalWidth, finalHeight);
        ctx.fillStyle = '#1890ff';

        months.forEach((month, index) => {
            const hours = monthlyStats[month] / 60;
            const barHeight = maxHours > 0 ? (hours / maxHours) * chartHeight : 0;
            const x = padding.left + index * barSpacing + (barSpacing - barWidth) / 2;
            const y = padding.top + chartHeight - barHeight;

            ctx.fillRect(x, y, barWidth, barHeight);

            ctx.fillStyle = '#666';
            ctx.font = `${fontSize}px Arial`;
            ctx.textAlign = 'center';
            ctx.fillText(month.split('-')[1] + '月', x + barWidth / 2, finalHeight - 10);
            ctx.fillText(hours.toFixed(1) + 'h', x + barWidth / 2, y - 5);
            ctx.fillStyle = '#1890ff';
        });

        ctx.strokeStyle = '#ddd';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(padding.left, padding.top);
        ctx.lineTo(padding.left, padding.top + chartHeight);
        ctx.lineTo(padding.left + chartWidth, padding.top + chartHeight);
        ctx.stroke();

        ctx.fillStyle = '#999';
        ctx.font = `${labelFontSize}px Arial`;
        ctx.textAlign = 'right';
        for (let i = 0; i <= 4; i++) {
            const value = (maxHours / 4) * i;
            const y = padding.top + chartHeight - (i / 4) * chartHeight;
            ctx.fillText(value.toFixed(1), padding.left - 10, y + 3);
        }
    }

    // 获取标签趋势
    async function getTagTrend() {
        const selectedTag = document.getElementById('tagSelect').value;
        const startDate = document.getElementById('startDate').value + ' 00:00:00';
        const endDate = document.getElementById('endDate').value + ' 23:59:59';
        const resultArea = document.getElementById('resultArea');

        if (!selectedTag) {
            resultArea.innerHTML = '请先选择一个标签';
            return;
        }

        resultArea.innerHTML = '正在分析趋势...';

        try {
            let data = window.didaHelperData;
            if (!data) {
                data = await fetchCompletedTasks(startDate, endDate);
            }

            if (!data || !data.length) {
                resultArea.innerHTML = '未找到数据';
                return;
            }

            // 按月份统计
            const monthlyStats = {};

            // 生成时间范围内所有月份的列表
            const start = new Date(startDate);
            const end = new Date(endDate);
            const allMonths = [];
            const current = new Date(start.getFullYear(), start.getMonth(), 1);

            while (current <= end) {
                const monthKey = `${current.getFullYear()}-${String(current.getMonth() + 1).padStart(2, '0')}`;
                allMonths.push(monthKey);
                monthlyStats[monthKey] = 0;
                current.setMonth(current.getMonth() + 1);
            }

            // 统计每个月的实际数据
            data.forEach(item => {
                if (!item.startDate || !item.dueDate) return;
                if (!item.tags || !item.tags.includes(selectedTag)) return;

                const duration = getDuration(item.startDate, item.dueDate);
                const date = new Date(item.startDate);
                const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;

                if (monthlyStats.hasOwnProperty(monthKey)) {
                    monthlyStats[monthKey] += duration;
                }
            });

            // 生成趋势报告
            if (allMonths.length === 0) {
                resultArea.innerHTML = `标签"${selectedTag}"在选定时间范围内没有数据`;
                return;
            }

            let trendReport = `
                <h4>标签趋势：${selectedTag} <span class="copy-btn" id="copyTrend">复制</span></h4>
                <p>时间范围：${startDate.split(' ')[0]} 至 ${endDate.split(' ')[0]}</p>
            `;

            let totalHours = 0;
            allMonths.forEach(month => {
                const hours = monthlyStats[month] / 60;
                totalHours += hours;
                trendReport += `
                    <div class="trend-item">
                        <div class="trend-month">${month}</div>
                        <div class="trend-hours">${hours.toFixed(1)} 小时</div>
                    </div>
                `;
            });

            trendReport += `
                <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #eee;">
                    <strong>总计：${totalHours.toFixed(1)} 小时</strong>
                </div>
                <div class="trend-chart">
                    <canvas id="trendChart"></canvas>
                    <button class="chart-zoom-btn" id="zoomChartBtn">放大图表</button>
                </div>
            `;

            resultArea.innerHTML = trendReport;

            window.didaHelperTrendData = { months: allMonths, stats: monthlyStats };

            setTimeout(() => {
                drawTrendChart(allMonths, monthlyStats);
            }, 100);

            document.getElementById('zoomChartBtn').addEventListener('click', () => {
                showZoomedChart(allMonths, monthlyStats, selectedTag);
            });

            // 添加复制功能
            document.getElementById('copyTrend').addEventListener('click', () => {
                let textReport = `标签趋势：${selectedTag}\n`;
                textReport += `时间范围：${startDate.split(' ')[0]} 至 ${endDate.split(' ')[0]}\n\n`;

                allMonths.forEach(month => {
                    const hours = monthlyStats[month] / 60;
                    textReport += `${month}：${hours.toFixed(1)} 小时\n`;
                });

                textReport += `\n总计：${totalHours.toFixed(1)} 小时\n`;

                navigator.clipboard.writeText(textReport).then(() => {
                    const btn = document.getElementById('copyTrend');
                    const originalText = btn.textContent;
                    btn.textContent = '已复制';
                    setTimeout(() => {
                        btn.textContent = originalText;
                    }, 2000);
                }).catch(err => {
                    alert('复制失败：' + err.message);
                });
            });

        } catch (error) {
            resultArea.innerHTML = `分析失败：${error.message}`;
        }
    }

    // 等待页面加载完成后初始化
    if (window.location.hostname === 'dida365.com') {
        window.addEventListener('load', () => {
            setTimeout(createPanel, 1000);
        });
    }
})();
