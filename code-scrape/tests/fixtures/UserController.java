package com.demo.controller;

import com.demo.service.UserService;

// 用户接口
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    /* 查询用户
       支持按名字过滤 */
    public String find(String name) {
        String pattern = "/api/**"; // 通配路径写在字符串里
        return userService.find(name, pattern);
    }
}
